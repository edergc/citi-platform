"""Sends outbound notifications for each supported channel type.

Each sender takes the channel's decrypted config dict + a message, and
returns (success, error_message).
"""

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

import httpx

from app.services.email_templates import render_message


def send_email(
    config: dict, to: str, message: str, subject: str = "CITI Platform", html: str | None = None
) -> tuple[bool, str | None]:
    required = ("smtp_host", "smtp_port", "from_address")
    missing = [k for k in required if not config.get(k)]
    if missing:
        return False, f"Faltan campos de configuración: {', '.join(missing)}"

    mime = MIMEMultipart("alternative")
    mime["Subject"] = subject
    mime["From"] = formataddr((config.get("from_name") or "", config["from_address"]))
    mime["To"] = to
    mime.attach(MIMEText(message, "plain", "utf-8"))
    mime.attach(MIMEText(html or render_message(subject, message), "html", "utf-8"))

    try:
        with smtplib.SMTP(config["smtp_host"], int(config["smtp_port"]), timeout=15) as server:
            if config.get("use_tls"):
                server.starttls()
            if config.get("smtp_user"):
                server.login(config["smtp_user"], config.get("smtp_password", ""))
            server.sendmail(config["from_address"], [to], mime.as_string())
        return True, None
    except (smtplib.SMTPException, OSError, TimeoutError) as exc:
        return False, str(exc)


def send_telegram(config: dict, to: str, message: str) -> tuple[bool, str | None]:
    bot_token = config.get("bot_token")
    chat_id = to or config.get("chat_id")
    if not bot_token or not chat_id:
        return False, "Faltan bot_token o chat_id"

    try:
        response = httpx.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": message},
            timeout=15,
            trust_env=False,
        )
        if response.status_code != 200:
            return False, f"Telegram respondió {response.status_code}: {response.text[:300]}"
        return True, None
    except httpx.HTTPError as exc:
        return False, str(exc)


def send_teams(config: dict, to: str, message: str) -> tuple[bool, str | None]:
    webhook_url = config.get("webhook_url")
    if not webhook_url:
        return False, "Falta webhook_url"

    try:
        response = httpx.post(webhook_url, json={"text": message}, timeout=15, trust_env=False)
        if response.status_code >= 300:
            return False, f"Teams respondió {response.status_code}: {response.text[:300]}"
        return True, None
    except httpx.HTTPError as exc:
        return False, str(exc)


def send_whatsapp(config: dict, to: str, message: str) -> tuple[bool, str | None]:
    return False, "Envío de WhatsApp no configurado todavía (requiere credenciales de un proveedor, ej. Twilio/Meta Cloud API)"


SENDERS = {
    "email": send_email,
    "telegram": send_telegram,
    "teams": send_teams,
    "whatsapp": send_whatsapp,
}
