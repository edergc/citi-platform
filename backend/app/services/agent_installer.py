"""Builds a self-contained, per-server installer bundle for the CITI Agent.

Windows: bundles the agent source, a pre-baked Python runtime (embeddable distribution
with websockets/httpx/psutil already installed — see agent/vendor/, built offline-first
since many sede servers have no internet access), NSSM, and a PowerShell script that
automates enrollment and service registration end to end — so installing on a new
server is "extract zip, run install.bat" with zero prerequisites, not even Python.

Linux: bundles the agent source, a bash script that creates a venv against the system's
own python3 (Oracle Linux and virtually every other distro ships one — unlike Windows
there's no need to vendor a whole runtime), and pre-downloaded wheels for
websockets+psutil+httpx and httpx's own transitive deps (see agent/vendor/linux-wheels/
— psutil ships a single cp36-abi3 wheel good for every Python 3.6+, and httpx plus its
dependency chain are all pure-Python py3-none-any wheels, so one copy of each covers
every version; only websockets doesn't use the stable ABI, so we carry one wheel per
CPython minor version, 3.8 through 3.13, manylinux x86_64) so install.sh works with zero
internet access on the target server, same offline-first principle as the Windows path.
httpx is only used by enroll.py's one-time enrollment call, not by the agent itself, but
both live in the same venv. If the target's Python version or architecture isn't covered by the
bundled wheels, install.sh automatically falls back to a normal `pip install` from PyPI.
"""

import io
import tarfile
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
AGENT_DIR = REPO_ROOT / "agent"
VENDOR_PYTHON_DIR = AGENT_DIR / "vendor" / "python"
VENDOR_LINUX_WHEELS_DIR = AGENT_DIR / "vendor" / "linux-wheels"
NSSM_PATH = REPO_ROOT / "tools" / "nssm-2.24" / "win64" / "nssm.exe"

INSTALL_PS1_TEMPLATE = r"""# CITI Agent - instalador automatico, generado para __HOSTNAME__
# No edites este archivo a mano: los valores de abajo son unicos para este servidor
# (el token de enrolamiento solo funciona una vez).
$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot

$CoreUrl  = "__CORE_URL__"
$ServerId = "__SERVER_ID__"
$Token    = "__TOKEN__"
$Hostname = "__HOSTNAME__"
$Python   = "$Root\python\python.exe"

function Fail($msg) {
    Write-Host ""
    Write-Host "ERROR: $msg" -ForegroundColor Red
    Write-Host ""
    Read-Host "Presiona Enter para cerrar"
    exit 1
}

try {

Write-Host "== Instalador del Agente CITI para '$Hostname' ==" -ForegroundColor Cyan
Write-Host "Carpeta: $Root"
Write-Host ""

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Fail "Ejecuta este instalador como Administrador (clic derecho sobre install.bat -> 'Ejecutar como administrador')."
}

if (-not (Test-Path $Python)) {
    Fail "No se encontro el interprete de Python incluido en $Root\python. El .zip pudo extraerse incompleto; vuelve a descargarlo desde CITI y extrae todo de nuevo."
}
Write-Host "[1/4] Python incluido en el instalador (no se necesita instalar nada aparte)." -ForegroundColor Green

$CoreHost, $CorePort = ($CoreUrl -replace '^https?://', '') -split ':'
if (-not $CorePort) { $CorePort = 80 }
Write-Host "[2/4] Verificando conectividad de red hacia $CoreHost`:$CorePort..." -ForegroundColor Cyan
$netTest = Test-NetConnection -ComputerName $CoreHost -Port $CorePort -WarningAction SilentlyContinue
if (-not $netTest.TcpTestSucceeded) {
    Fail "Este servidor no puede alcanzar $CoreHost`:$CorePort por red. Revisa firewall/proxy de salida antes de continuar (el enrolamiento y los latidos del agente pasan por esa misma conexion)."
}
Write-Host "Conectividad OK." -ForegroundColor Green

Write-Host "[3/4] Enrolando el agente con CITI Core ($CoreUrl)..." -ForegroundColor Cyan
& $Python "$Root\enroll.py" --core-url $CoreUrl --server-id $ServerId --token $Token
if ($LASTEXITCODE -ne 0) {
    Fail "El enrolamiento fallo. El token pudo haber expirado o ya haberse usado; genera uno nuevo desde CITI (boton 'Descargar instalador') y vuelve a intentar."
}

Write-Host "[4/4] Registrando el servicio de Windows 'CitiAgent'..." -ForegroundColor Cyan
$nssm = "$Root\nssm.exe"
$logsDir = "$Root\logs"
New-Item -ItemType Directory -Force -Path $logsDir | Out-Null
$stdoutLog = "$logsDir\service-stdout.log"
$stderrLog = "$logsDir\service-stderr.log"
Remove-Item -Force -ErrorAction SilentlyContinue $stdoutLog, $stderrLog

# nssm.exe writes to stderr for perfectly normal cases (e.g. "service doesn't exist yet"
# when checking). Under $ErrorActionPreference = "Stop" that gets treated as a terminating
# exception even when redirected, so this whole block runs with errors relaxed and relies
# on explicit exit-code / Get-Service checks instead of exceptions.
$prevErrorPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"

$existingService = Get-Service -Name CitiAgent -ErrorAction SilentlyContinue
if ($existingService) {
    Write-Host "El servicio 'CitiAgent' ya existia en este servidor; se detiene y reconfigura." -ForegroundColor Yellow
    & $nssm stop CitiAgent | Out-Null
    & $nssm remove CitiAgent confirm | Out-Null
}

& $nssm install CitiAgent $Python | Out-Null
$installExitCode = $LASTEXITCODE
& $nssm set CitiAgent AppDirectory "$Root" | Out-Null
& $nssm set CitiAgent AppParameters "-u citi_agent.py" | Out-Null
& $nssm set CitiAgent AppStdout $stdoutLog | Out-Null
& $nssm set CitiAgent AppStderr $stderrLog | Out-Null
& $nssm set CitiAgent Start SERVICE_AUTO_START | Out-Null
& $nssm start CitiAgent | Out-Null

$ErrorActionPreference = $prevErrorPreference

if ($installExitCode -ne 0) { Fail "nssm.exe no pudo registrar el servicio 'CitiAgent' (codigo $installExitCode)." }

Write-Host "Esperando a que el agente confirme la conexion..." -ForegroundColor Cyan
$connected = $false
for ($i = 0; $i -lt 10; $i++) {
    Start-Sleep -Seconds 1
    if ((Test-Path $stdoutLog) -and (Select-String -Path $stdoutLog -Pattern "conectado a CITI Core" -Quiet)) {
        $connected = $true
        break
    }
}

$svc = Get-Service -Name CitiAgent -ErrorAction SilentlyContinue
if (-not $svc -or $svc.Status -ne "Running") {
    Fail "El servicio 'CitiAgent' no llego a estado 'Running'. Revisa $stderrLog para el detalle."
}
if (-not $connected) {
    Write-Host ""
    Write-Host "El servicio esta corriendo, pero todavia no confirma conexion a CITI Core." -ForegroundColor Yellow
    Write-Host "Salida reciente del agente:" -ForegroundColor Yellow
    if (Test-Path $stdoutLog) { Get-Content $stdoutLog -Tail 10 | ForEach-Object { Write-Host "  $_" } }
    if (Test-Path $stderrLog) { Get-Content $stderrLog -Tail 10 | ForEach-Object { Write-Host "  $_" -ForegroundColor Red } }
    Write-Host ""
    Write-Host "Puede tardar unos segundos mas por su cuenta, o puede indicar un problema de red/firewall hacia $CoreHost`:$CorePort." -ForegroundColor Yellow
} else {
    Write-Host ""
    Write-Host "Listo. El Agente CITI esta corriendo y conectado a CITI Core desde '$Hostname'." -ForegroundColor Green
    Write-Host "Verifica en el panel CITI -> Servidores -> $Hostname que aparezca 'Agente activo'." -ForegroundColor Green
}

} catch {
    Fail "Error inesperado: $($_.Exception.Message)"
}

Write-Host ""
Read-Host "Presiona Enter para cerrar"
"""

INSTALL_BAT = r"""@echo off
setlocal
:: Se relanza como Administrador si hace falta, y ejecuta install.ps1 sin
:: restricciones de ExecutionPolicy. No necesitas abrir PowerShell manualmente:
:: solo doble clic aqui.
net session >nul 2>&1
if %errorLevel% neq 0 (
    powershell -NoProfile -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
if %errorLevel% neq 0 (
    echo.
    echo El instalador termino con un error. Revisa el mensaje de arriba.
    pause
)
"""


def build_agent_installer_zip(*, core_url: str, server_id: str, token: str, hostname: str) -> bytes:
    install_ps1 = (
        INSTALL_PS1_TEMPLATE.replace("__CORE_URL__", core_url)
        .replace("__SERVER_ID__", server_id)
        .replace("__TOKEN__", token)
        .replace("__HOSTNAME__", hostname)
    )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(AGENT_DIR / "citi_agent.py", "citi_agent.py")
        zf.write(AGENT_DIR / "enroll.py", "enroll.py")
        zf.write(NSSM_PATH, "nssm.exe")
        zf.writestr("install.ps1", install_ps1)
        zf.writestr("install.bat", INSTALL_BAT)
        for path in VENDOR_PYTHON_DIR.rglob("*"):
            if path.is_file():
                zf.write(path, str(Path("python") / path.relative_to(VENDOR_PYTHON_DIR)))
    return buffer.getvalue()


INSTALL_SH_TEMPLATE = r"""#!/usr/bin/env bash
# CITI Agent - instalador automatico, generado para __HOSTNAME__ (Linux)
# No edites este archivo a mano: los valores de abajo son unicos para este servidor
# (el token de enrolamiento solo funciona una vez).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CORE_URL="__CORE_URL__"
SERVER_ID="__SERVER_ID__"
TOKEN="__TOKEN__"
HOSTNAME_LABEL="__HOSTNAME__"
INSTALL_DIR="/opt/citi-agent"

fail() {
    echo ""
    echo "ERROR: $1" >&2
    echo ""
    exit 1
}

echo "== Instalador del Agente CITI para '$HOSTNAME_LABEL' (Linux) =="
echo "Carpeta: $ROOT"
echo ""

if [ "$(id -u)" -ne 0 ]; then
    fail "Ejecuta este instalador como root (sudo ./install.sh). El agente necesita permisos de root para poder iniciar/detener/reiniciar otros servicios del sistema."
fi

if ! command -v python3 >/dev/null 2>&1; then
    fail "No se encontro python3. Instalalo primero (Oracle Linux: sudo dnf install -y python3) y vuelve a ejecutar este instalador."
fi
echo "[1/5] python3 disponible: $(python3 --version)"

echo "[2/5] Verificando conectividad de red hacia CITI Core ($CORE_URL)..."
CORE_HOST_PORT="${CORE_URL#http://}"
CORE_HOST_PORT="${CORE_HOST_PORT#https://}"
CORE_HOST="${CORE_HOST_PORT%%:*}"
CORE_PORT="${CORE_HOST_PORT##*:}"
if [ "$CORE_PORT" = "$CORE_HOST" ]; then CORE_PORT=80; fi
if ! timeout 5 bash -c "cat < /dev/null > /dev/tcp/$CORE_HOST/$CORE_PORT" 2>/dev/null; then
    fail "Este servidor no puede alcanzar $CORE_HOST:$CORE_PORT por red. Revisa firewall/proxy de salida antes de continuar (el enrolamiento y los latidos del agente pasan por esa misma conexion)."
fi
echo "Conectividad OK."

echo "[3/5] Instalando en $INSTALL_DIR y preparando el entorno de Python..."
mkdir -p "$INSTALL_DIR"
cp "$ROOT/citi_agent.py" "$ROOT/enroll.py" "$INSTALL_DIR/"
python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install --quiet --upgrade pip >/dev/null 2>&1 || true

# Prefer the wheels bundled in this package (no internet needed on the target server —
# same offline-first approach as the Windows installer). Only falls back to PyPI if this
# server's Python version/architecture isn't one of the ones we bundled for. httpx is
# only used by enroll.py (one-time enrollment call), not by the agent itself, but both
# scripts live in the same venv so it has to be installed too.
if [ -d "$ROOT/wheels" ] && "$INSTALL_DIR/venv/bin/pip" install --quiet --no-index --find-links "$ROOT/wheels" websockets psutil httpx 2>/dev/null; then
    echo "Dependencias instaladas desde los paquetes incluidos (sin necesidad de internet)."
elif "$INSTALL_DIR/venv/bin/pip" install --quiet websockets psutil httpx; then
    echo "Dependencias instaladas desde PyPI (los paquetes incluidos no eran compatibles con este Python/arquitectura)."
else
    fail "No se pudieron instalar las dependencias (websockets, psutil, httpx). Los paquetes incluidos en el instalador no son compatibles con este servidor (revisa version de Python: $(python3 --version), arquitectura: $(uname -m)) y tampoco hay salida a internet/PyPI. Instalalas manualmente en $INSTALL_DIR/venv y vuelve a correr este script."
fi

echo "[4/5] Enrolando el agente con CITI Core ($CORE_URL)..."
if ! "$INSTALL_DIR/venv/bin/python" "$INSTALL_DIR/enroll.py" --core-url "$CORE_URL" --server-id "$SERVER_ID" --token "$TOKEN"; then
    fail "El enrolamiento fallo. El token pudo haber expirado o ya haberse usado; genera uno nuevo desde CITI (boton 'Descargar instalador') y vuelve a intentar."
fi

echo "[5/5] Registrando el servicio systemd 'citi-agent'..."
cat > /etc/systemd/system/citi-agent.service <<UNIT
[Unit]
Description=CITI Platform - Agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/venv/bin/python -u citi_agent.py
Restart=always
RestartSec=5
User=root

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable --now citi-agent >/dev/null

echo "Esperando a que el agente confirme la conexion..."
CONNECTED=0
for i in $(seq 1 10); do
    sleep 1
    if journalctl -u citi-agent -n 20 --no-pager 2>/dev/null | grep -q "conectado a CITI Core"; then
        CONNECTED=1
        break
    fi
done

if ! systemctl is-active --quiet citi-agent; then
    fail "El servicio 'citi-agent' no llego a estado activo. Revisa: journalctl -u citi-agent -n 50"
fi

if [ "$CONNECTED" -eq 1 ]; then
    echo ""
    echo "Listo. El Agente CITI esta corriendo y conectado a CITI Core desde '$HOSTNAME_LABEL'."
    echo "Verifica en el panel CITI -> Servidores -> $HOSTNAME_LABEL que aparezca 'Agente activo'."
else
    echo ""
    echo "El servicio esta corriendo, pero todavia no confirma conexion a CITI Core."
    echo "Puede tardar unos segundos mas por su cuenta, o puede indicar un problema de red/firewall."
    echo "Sigue el log en vivo con: journalctl -u citi-agent -f"
fi
"""


def build_agent_installer_targz(*, core_url: str, server_id: str, token: str, hostname: str) -> bytes:
    install_sh = (
        INSTALL_SH_TEMPLATE.replace("__CORE_URL__", core_url)
        .replace("__SERVER_ID__", server_id)
        .replace("__TOKEN__", token)
        .replace("__HOSTNAME__", hostname)
    )

    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tf:
        tf.add(AGENT_DIR / "citi_agent.py", arcname="citi_agent.py")
        tf.add(AGENT_DIR / "enroll.py", arcname="enroll.py")
        for wheel_path in VENDOR_LINUX_WHEELS_DIR.glob("*.whl"):
            tf.add(wheel_path, arcname=str(Path("wheels") / wheel_path.name))

        script_bytes = install_sh.encode("utf-8")
        info = tarfile.TarInfo(name="install.sh")
        info.size = len(script_bytes)
        info.mode = 0o755  # executable — sudo ./install.sh works without a separate chmod
        tf.addfile(info, io.BytesIO(script_bytes))
    return buffer.getvalue()
