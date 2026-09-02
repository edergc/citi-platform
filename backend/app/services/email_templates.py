"""Branded HTML email templates for CITI Platform outbound notifications.

All emails route through send_email() in notification_senders.py, which wraps
plain-text messages with render_message() unless a caller supplies its own
html (e.g. render_password_reset() for the reset-password flow).
"""

from html import escape

_BRAND_RED = "#7f1d1d"
_BRAND_RED_DARK = "#450a0a"
_BRAND_AMBER = "#f59e0b"
_TEXT_DARK = "#1e293b"
_TEXT_MUTED = "#64748b"
_BORDER = "#e2e8f0"
_BG = "#f1f5f9"


def _shell(preheader: str, body_html: str) -> str:
    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CITI Platform</title>
</head>
<body style="margin:0;padding:0;background-color:{_BG};font-family:'Segoe UI',Arial,sans-serif;">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;">{escape(preheader)}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:{_BG};padding:32px 16px;">
<tr><td align="center">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;background-color:#ffffff;border-radius:12px;overflow:hidden;border:1px solid {_BORDER};">
<tr>
<td style="background:linear-gradient(135deg,{_BRAND_RED_DARK},{_BRAND_RED});padding:28px 32px;">
<table role="presentation" cellpadding="0" cellspacing="0">
<tr>
<td style="width:44px;vertical-align:middle;">
<div style="width:40px;height:40px;border-radius:50%;background:rgba(0,0,0,0.2);border:1px solid rgba(245,158,11,0.5);text-align:center;line-height:40px;font-size:18px;">&#9878;</div>
</td>
<td style="padding-left:12px;vertical-align:middle;">
<p style="margin:0;font-size:11px;letter-spacing:1px;text-transform:uppercase;color:{_BRAND_AMBER};font-weight:600;">Poder Judicial del Perú</p>
<p style="margin:2px 0 0;font-size:14px;color:#ffffff;font-weight:600;">Corte Superior de Justicia de Lima</p>
</td>
</tr>
</table>
</td>
</tr>
<tr>
<td style="padding:32px;">
{body_html}
</td>
</tr>
<tr>
<td style="padding:20px 32px;background-color:#f8fafc;border-top:1px solid {_BORDER};">
<p style="margin:0;font-size:12px;color:{_TEXT_MUTED};">Coordinación de Informática — Corte Superior de Justicia de Lima</p>
<p style="margin:4px 0 0;font-size:11px;color:{_TEXT_MUTED};">Este es un mensaje automático de CITI Platform. Por favor no respondas a este correo.</p>
</td>
</tr>
</table>
</td></tr>
</table>
</body>
</html>"""


def render_message(subject: str, message: str) -> str:
    """Wrap an arbitrary plain-text message (e.g. alert/notification tests) in the branded shell."""
    paragraphs_html = "".join(
        f'<p style="margin:0 0 14px;font-size:14px;line-height:1.6;color:{_TEXT_DARK};">'
        f'{escape(paragraph).replace(chr(10), "<br>")}</p>'
        for paragraph in message.split("\n\n")
        if paragraph.strip()
    )
    body = (
        f'<p style="margin:0 0 20px;font-size:18px;font-weight:600;color:{_TEXT_DARK};">{escape(subject)}</p>'
        f"{paragraphs_html}"
    )
    return _shell(subject, body)


_SEVERITY_COLORS = {
    "critical": "#dc2626",
    "warning": "#f59e0b",
    "info": "#3b82f6",
}
_SEVERITY_LABELS = {
    "critical": "CRÍTICO",
    "warning": "ADVERTENCIA",
    "info": "INFORMATIVO",
}


def render_incident_email(title: str, message: str, severity: str) -> str:
    color = _SEVERITY_COLORS.get(severity, _TEXT_MUTED)
    label = _SEVERITY_LABELS.get(severity, severity.upper())
    body = f"""
<p style="margin:0 0 16px;">
  <span style="display:inline-block;padding:3px 10px;border-radius:999px;background-color:{color};color:#ffffff;font-size:11px;font-weight:700;letter-spacing:0.5px;">{escape(label)}</span>
</p>
<p style="margin:0 0 16px;font-size:18px;font-weight:600;color:{_TEXT_DARK};">{escape(title)}</p>
<p style="margin:0;font-size:14px;line-height:1.6;color:{_TEXT_DARK};white-space:pre-line;">{escape(message)}</p>
"""
    return _shell(title, body)


def render_weekly_report_email(report: dict) -> str:
    scope_label = report["site_name"] or "Resumen global"
    period = f"{report['window_start'].strftime('%d/%m/%Y')} – {report['window_end'].strftime('%d/%m/%Y')}"

    severity_rows = "".join(
        f'<tr><td style="padding:6px 0;font-size:13px;color:{_TEXT_MUTED};">{escape(_SEVERITY_LABELS.get(sev, sev.upper()))}</td>'
        f'<td style="padding:6px 0;font-size:13px;font-weight:600;color:{_TEXT_DARK};text-align:right;">{count}</td></tr>'
        for sev, count in report["open_alerts_by_severity"].items()
    )

    def _stat_row(label: str, value: object, shaded: bool) -> str:
        bg = f"background-color:{_BG};" if shaded else ""
        return (
            f'<tr style="{bg}"><td style="padding:12px 16px;font-size:12px;color:{_TEXT_MUTED};">{escape(label)}</td>'
            f'<td style="padding:12px 16px;font-size:13px;font-weight:600;color:{_TEXT_DARK};text-align:right;">{value}</td></tr>'
        )

    stats_html = (
        _stat_row("Servidores en línea", f"{report['servers_online']} / {report['servers_total']}", True)
        + _stat_row("Servidores desconectados", report["servers_offline"], False)
        + _stat_row("Fallos de backup (7 días)", report["backup_failures"], True)
        + _stat_row("Alertas abiertas sin reconocer", report["unacknowledged_open_alerts"], False)
    )

    def _detail_section(title: str, rows: list[str]) -> str:
        if not rows:
            return ""
        items_html = "".join(
            f'<li style="margin:0 0 6px;font-size:13px;line-height:1.5;color:{_TEXT_DARK};">{row}</li>' for row in rows
        )
        return (
            f'<p style="margin:20px 0 8px;font-size:13px;font-weight:600;color:{_TEXT_DARK};">{escape(title)}</p>'
            f'<ul style="margin:0;padding-left:18px;">{items_html}</ul>'
        )

    offline_rows = [
        f"<strong>{escape(s['hostname'])}</strong>" for s in report.get("offline_servers", [])
    ]
    alert_rows = [
        f"<strong>{escape(a['hostname'] or 'Sin servidor')}</strong> — {escape(a['rule_name'])}"
        f"{' (sin reconocer)' if not a['acknowledged'] else ''}"
        for a in report.get("open_alerts", [])
    ]
    backup_rows = [
        f"<strong>{escape(b['service_name'])}</strong>"
        + (f" — {escape(b['error_message'][:120])}" if b.get("error_message") else "")
        for b in report.get("failed_backups", [])
    ]

    body = f"""
<p style="margin:0 0 4px;font-size:11px;letter-spacing:0.5px;text-transform:uppercase;color:{_TEXT_MUTED};font-weight:600;">Reporte semanal &mdash; {escape(period)}</p>
<p style="margin:0 0 20px;font-size:18px;font-weight:600;color:{_TEXT_DARK};">{escape(scope_label)}</p>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 20px;border:1px solid {_BORDER};border-radius:8px;overflow:hidden;">
{stats_html}
</table>
<p style="margin:0 0 8px;font-size:13px;font-weight:600;color:{_TEXT_DARK};">Alertas abiertas por severidad</p>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:0;">
{severity_rows}
</table>
{_detail_section("Servidores desconectados", offline_rows)}
{_detail_section("Alertas abiertas", alert_rows)}
{_detail_section("Backups fallidos (7 días)", backup_rows)}
"""
    return _shell(f"Reporte semanal — {scope_label}", body)


def render_password_reset(full_name: str, reset_url: str) -> str:
    body = f"""
<p style="margin:0 0 20px;font-size:18px;font-weight:600;color:{_TEXT_DARK};">Restablecer contraseña</p>
<p style="margin:0 0 16px;font-size:14px;line-height:1.6;color:{_TEXT_DARK};">Hola {escape(full_name)},</p>
<p style="margin:0 0 24px;font-size:14px;line-height:1.6;color:{_TEXT_DARK};">
Recibimos una solicitud para restablecer tu contraseña en <strong>CITI Platform</strong>, el sistema de
administración de la Coordinación de Informática. Haz clic en el siguiente botón para elegir una nueva
contraseña. Este enlace es válido por 1 hora.
</p>
<table role="presentation" cellpadding="0" cellspacing="0" style="margin:0 0 24px;">
<tr><td style="border-radius:8px;background-color:{_BRAND_AMBER};">
<a href="{escape(reset_url)}" style="display:inline-block;padding:12px 28px;font-size:14px;font-weight:600;color:{_BRAND_RED_DARK};text-decoration:none;border-radius:8px;">
Restablecer contraseña
</a>
</td></tr>
</table>
<p style="margin:0 0 8px;font-size:12px;line-height:1.6;color:{_TEXT_MUTED};">Si el botón no funciona, copia y pega este enlace en tu navegador:</p>
<p style="margin:0 0 20px;font-size:12px;line-height:1.6;word-break:break-all;color:#2563eb;">{escape(reset_url)}</p>
<p style="margin:0;font-size:13px;line-height:1.6;color:{_TEXT_MUTED};">Si no solicitaste este cambio, puedes ignorar este correo con tranquilidad.</p>
"""
    return _shell("Restablecer contraseña — CITI Platform", body)
