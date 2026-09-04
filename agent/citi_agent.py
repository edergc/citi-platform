"""CITI Agent: maintains a persistent connection to CITI Core and executes
start/stop/restart commands for the services this server's agent was told
about at connect time (allowlist, not free-form commands).

Runs on both Windows and Linux — the metrics/websocket/backup machinery below is
identical on both (mostly psutil + stdlib), only service control, the shell used for
deploy build commands, PostgreSQL client tool paths, and critical-event collection
differ, gated by IS_WINDOWS.

`from __future__ import annotations` matters here specifically: unlike the backend
(always Python 3.12), this file runs on whatever python3 the target server happens to
ship — Oracle Linux 9's default is 3.9, which doesn't support evaluating `X | None`
union syntax at runtime (that needs 3.10+, PEP 604). Deferring annotations to strings
sidesteps that without hand-converting every `X | None` to `Optional[X]`.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import psutil
import websockets

IS_WINDOWS = platform.system() == "Windows"
AGENT_VERSION = "1.8.1"

CONFIG_PATH = Path(__file__).parent / "agent_config.json"
SERVICE_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")
DB_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_-]+$")
HEARTBEAT_INTERVAL_SECONDS = 15
RECONNECT_DELAY_SECONDS = 5
HTTP_CHECK_TIMEOUT_SECONDS = 10
EXCLUDED_DIR_NAMES = {"node_modules", "venv", ".venv", ".git", "__pycache__", "dist", "logs", ".next", "build"}
# Windows has no reliable PATH convention for PostgreSQL client tools on a fresh server,
# so we point at the fixed install location; Linux installs them via the distro package
# manager, which does put them on PATH — see _pg_tool().
PG_BIN = Path(r"C:\Program Files\PostgreSQL\16\bin") if IS_WINDOWS else None

# Processes and critical system events are only re-sampled every ~60s (4x the heartbeat
# interval) — enumerating processes and querying the event log/journal have real cost on
# a busy server, unlike the cheap single-syscall rate counters below.
PROCESS_REFRESH_SECONDS = 60
EVENTS_REFRESH_SECONDS = 60
CRITICAL_EVENT_LOGS = ["System", "Application"]  # Windows Event Log channels only
TOP_PROCESS_COUNT = 5

# Continuous network-path diagnostics (PingPlotter-style): a full traceroute cycle to
# Core runs every NETWORK_PATH_INTERVAL_SECONDS, on its own task (see network_path_loop)
# rather than inline in collect_metrics() — unlike process/event sampling, a traceroute
# can take real seconds in the worst case (timed-out hops), and blocking the heartbeat
# on it risks delaying/looking like a dropped connection, which would be a bad irony for
# a network-diagnostics feature. 60s (not PingPlotter's real ~1-2.5s) keeps this
# sustainable running forever across the whole fleet.
#
# History: the first implementation (through 2026-08-11) built ICMP packets directly
# over a raw socket in this process. Two servers at the same site (SEDE MIROQUESADA,
# SRVMARQUEZEJE) fell into ~14h of continuous connection flapping (disconnect/reconnect
# every 2-5 min) after picking it up — the traceroute cycles themselves completed
# cleanly and fast (no timeouts), so it wasn't a slow-probe-blocks-heartbeat problem;
# leading theory is that this process rapidly opening raw ICMP sockets tripped
# security software on that site's machines into resetting the process's OTHER
# connections (the websocket to Core). Never confirmed directly, but not worth
# re-risking: this now shells out to the OS's own `ping` (present on every Windows and
# Linux box, no extra package needed, unlike traceroute/mtr) for each TTL instead —
# a well-known system binary doing ICMP work is unremarkable to security software,
# whereas this process doing it directly, at volume, apparently was not. Parses ping's
# text output by shape (IP-address pattern, "N ms" pattern, the blank line before the
# summary section) rather than by matching English/Spanish words, so it doesn't care
# what locale the OS is running in.
NETWORK_PATH_ENABLED = True
NETWORK_PATH_INTERVAL_SECONDS = 60
TRACEROUTE_MAX_HOPS = 20
TRACEROUTE_PROBES_PER_HOP = 3
TRACEROUTE_TIMEOUT_SECONDS = 1.5

# Physical disk health (SMART). Kill switch included from the start this time — see
# the network-path history note above for exactly why that's worth the one extra
# constant. Interval is long (30 min, not seconds) on purpose: wear/power-on-hours
# change over weeks, not minutes, and shelling out rarely is inherently gentler than
# what caused that earlier incident. Reads through smartctl (Linux) / the built-in
# Storage Management PowerShell module (Windows) — both well-known system tooling,
# never a from-scratch device probe — and both are asked for JSON output specifically
# so parsing never depends on the OS's display language.
SMART_ENABLED = True
SMART_CHECK_INTERVAL_SECONDS = 1800


def _pg_tool(name: str) -> str:
    """Path/command to invoke a PostgreSQL client tool (pg_dump, createdb, pg_restore)."""
    return str(PG_BIN / f"{name}.exe") if IS_WINDOWS else name


def load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text())


def build_ws_url(config: dict) -> str:
    core_url = config["core_url"]
    scheme = "wss" if core_url.startswith("https") else "ws"
    host = core_url.split("://", 1)[1]
    return f"{scheme}://{host}/api/v1/agents/ws?token={config['agent_token']}"


def _resolve_core_target(core_url: str) -> str:
    """Bare host/IP to run the network-path probe against — the same host this agent
    already connects its websocket to, with scheme/port/path stripped."""
    host_port = core_url.split("://", 1)[-1].split("/", 1)[0]
    return host_port.split(":", 1)[0]


def run_service_command(control_identifier: str, action: str) -> tuple[bool, str]:
    if not SERVICE_NAME_RE.match(control_identifier):
        return False, f"Nombre de servicio inválido: {control_identifier}"

    if IS_WINDOWS:
        cmdlet = {
            "start": f"Start-Service -Name '{control_identifier}'",
            "stop": f"Stop-Service -Name '{control_identifier}' -Force",
            "restart": f"Restart-Service -Name '{control_identifier}' -Force",
            "force_restart": f"Restart-Service -Name '{control_identifier}' -Force",
        }.get(action)
        if cmdlet is None:
            return False, f"Acción no soportada: {action}"
        command = ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmdlet]
    else:
        systemctl_action = {"start": "start", "stop": "stop", "restart": "restart", "force_restart": "restart"}.get(
            action
        )
        if systemctl_action is None:
            return False, f"Acción no soportada: {action}"
        command = ["systemctl", systemctl_action, control_identifier]

    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        return False, "Tiempo de espera agotado ejecutando el comando"

    output = (result.stdout + result.stderr).strip()
    return result.returncode == 0, output or f"OK ({action})"


def _iter_backup_files(source: Path):
    for path in source.rglob("*"):
        if path.is_dir():
            continue
        if any(part in EXCLUDED_DIR_NAMES for part in path.relative_to(source).parts[:-1]):
            continue
        yield path


def run_backup(source_path: str, storage_path: str) -> tuple[bool, dict]:
    source = Path(source_path)
    if not source.is_dir():
        return False, {"error": f"La ruta de origen no existe: {source_path}"}

    dest_dir = Path(storage_path)
    dest_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    zip_path = dest_dir / f"{source.name}-{timestamp}.zip"

    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for file_path in _iter_backup_files(source):
                zf.write(file_path, file_path.relative_to(source))
    except OSError as exc:
        return False, {"error": f"Error creando el respaldo: {exc}"}

    sha256 = hashlib.sha256()
    with open(zip_path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            sha256.update(chunk)

    return True, {
        "size_bytes": zip_path.stat().st_size,
        "sha256_hash": sha256.hexdigest(),
        "storage_path": str(zip_path),
    }


def run_restore(zip_path: str, target_path: str) -> tuple[bool, dict]:
    zip_file = Path(zip_path)
    if not zip_file.is_file():
        return False, {"error": f"No se encontró el archivo de respaldo: {zip_path}"}

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    restore_dir = Path(target_path) / "restored" / timestamp
    restore_dir.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(zip_file, "r") as zf:
            zf.extractall(restore_dir)
    except (OSError, zipfile.BadZipFile) as exc:
        return False, {"error": f"Error restaurando el respaldo: {exc}"}

    return True, {"restored_to_path": str(restore_dir)}


_NO_PROXY_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def run_http_check(url: str) -> dict:
    """Synthetic reachability probe — this server's Agent acting as a Datadog-style
    "private location" for Core's per-sede monitoring (see
    backend/app/services/synthetic_checks.py). Stdlib-only (urllib), deliberately no new
    dependency to bundle into the installer. Success = HTTP 200-399; anything else
    (including a network-level failure) is reported as a failure with the reason, never
    raised — this always returns a result dict, it's Core's job to interpret it.

    Explicitly bypasses any HTTP_PROXY/HTTPS_PROXY set on this machine (urllib.request
    reads those from the environment by default) — a corporate outbound proxy is set
    machine-wide on some of these servers, and routing through it would silently test
    reachability from the proxy's own network path instead of this sede's, defeating the
    entire point of a per-sede probe."""
    request = urllib.request.Request(url, headers={"User-Agent": "CITI-Agent-SyntheticCheck"})
    started = time.monotonic()
    try:
        with _NO_PROXY_OPENER.open(request, timeout=HTTP_CHECK_TIMEOUT_SECONDS) as response:
            status_code = response.status
    except urllib.error.HTTPError as exc:
        # A real HTTP response with an error status (4xx/5xx) — still reachable, just
        # unhealthy, so it's worth reporting the real code rather than a generic failure.
        status_code = exc.code
    except urllib.error.URLError as exc:
        latency_ms = (time.monotonic() - started) * 1000
        return {"success": False, "status_code": None, "latency_ms": round(latency_ms, 1), "error": str(exc.reason)}
    except Exception as exc:  # noqa: BLE001 - never let a bad URL/timeout kill the caller
        latency_ms = (time.monotonic() - started) * 1000
        return {"success": False, "status_code": None, "latency_ms": round(latency_ms, 1), "error": str(exc)}

    latency_ms = (time.monotonic() - started) * 1000
    success = 200 <= status_code < 400
    return {
        "success": success,
        "status_code": status_code,
        "latency_ms": round(latency_ms, 1),
        "error": None if success else f"código HTTP {status_code}",
    }


def _git(repo_path: str, args: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", repo_path] + args, capture_output=True, text=True, timeout=timeout)


def _authed_fetch_url(repo_url: str, token: str) -> str:
    if repo_url.startswith("https://"):
        return f"https://{token}@{repo_url[len('https://') :]}"
    return repo_url


def get_git_status(repo_path: str, repo_url: str, branch: str, token: str) -> dict:
    if not (Path(repo_path) / ".git").is_dir():
        return {"error": f"No es un repositorio git: {repo_path}"}

    status_result = _git(repo_path, ["status", "--porcelain"])
    dirty_files = [line[3:] for line in status_result.stdout.splitlines() if line.strip()]

    try:
        fetch_result = _git(repo_path, ["fetch", _authed_fetch_url(repo_url, token), branch], timeout=60)
    except subprocess.TimeoutExpired:
        return {"is_dirty": bool(dirty_files), "dirty_files": dirty_files, "error": "git fetch superó el tiempo límite"}
    if fetch_result.returncode != 0:
        return {
            "is_dirty": bool(dirty_files),
            "dirty_files": dirty_files,
            "error": f"git fetch falló: {fetch_result.stderr.strip()[:500]}",
        }

    current = _git(repo_path, ["rev-parse", "HEAD"]).stdout.strip()
    remote = _git(repo_path, ["rev-parse", "FETCH_HEAD"]).stdout.strip()
    count_result = _git(repo_path, ["rev-list", f"{current}..{remote}", "--count"])
    try:
        commits_behind = int(count_result.stdout.strip() or 0)
    except ValueError:
        commits_behind = 0

    return {
        "is_dirty": bool(dirty_files),
        "dirty_files": dirty_files,
        "current_commit": current,
        "remote_commit": remote,
        "commits_behind": commits_behind,
    }


def run_deploy(
    repo_path: str, repo_url: str, branch: str, target_commit: str | None, build_command: str | None, token: str
) -> tuple[bool, dict]:
    if not (Path(repo_path) / ".git").is_dir():
        return False, {"error": f"No es un repositorio git: {repo_path}"}

    # Defense in depth: refuse a dirty tree even if Core already checked, in case
    # something changed on disk between the check and this call.
    status_result = _git(repo_path, ["status", "--porcelain"])
    if status_result.stdout.strip():
        return False, {"error": "El árbol de trabajo tiene cambios sin confirmar; despliegue cancelado por seguridad."}

    try:
        fetch_result = _git(repo_path, ["fetch", _authed_fetch_url(repo_url, token), branch], timeout=60)
    except subprocess.TimeoutExpired:
        return False, {"error": "git fetch superó el tiempo límite"}
    if fetch_result.returncode != 0:
        return False, {"error": f"git fetch falló: {fetch_result.stderr.strip()[:500]}"}

    if target_commit:
        checkout_result = _git(repo_path, ["checkout", "--detach", target_commit])
        if checkout_result.returncode != 0:
            return False, {"error": f"git checkout falló: {checkout_result.stderr.strip()[:500]}"}
    else:
        checkout_branch = _git(repo_path, ["checkout", branch])
        if checkout_branch.returncode != 0:
            return False, {"error": f"git checkout {branch} falló: {checkout_branch.stderr.strip()[:500]}"}
        merge_result = _git(repo_path, ["merge", "--ff-only", "FETCH_HEAD"])
        if merge_result.returncode != 0:
            return False, {"error": f"git merge --ff-only falló (¿la rama diverge?): {merge_result.stderr.strip()[:500]}"}

    new_commit = _git(repo_path, ["rev-parse", "HEAD"]).stdout.strip()

    if not build_command:
        return True, {"new_commit": new_commit, "output": "OK (sin build_command)"}

    shell_command = (
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", build_command]
        if IS_WINDOWS
        else ["bash", "-c", build_command]
    )
    try:
        build_result = subprocess.run(
            shell_command,
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        return False, {"error": "El comando de build superó el tiempo límite (300s)", "new_commit": new_commit}

    output = (build_result.stdout + build_result.stderr)[-4000:]
    if build_result.returncode != 0:
        return False, {"error": f"El build falló (exit {build_result.returncode})", "output": output, "new_commit": new_commit}

    return True, {"new_commit": new_commit, "output": output}


def _pg_env(password: str) -> dict:
    env = os.environ.copy()
    env["PGPASSWORD"] = password
    return env


def run_backup_database(host: str, port: str, dbname: str, user: str, password: str, storage_path: str) -> tuple[bool, dict]:
    if not all(DB_IDENTIFIER_RE.match(v) for v in (dbname, user)):
        return False, {"error": "Nombre de base de datos o usuario inválido"}

    dest_dir = Path(storage_path)
    dest_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dump_path = dest_dir / f"{dbname}-{timestamp}.dump"

    try:
        result = subprocess.run(
            [
                _pg_tool("pg_dump"),
                "-h", host, "-p", str(port), "-U", user,
                "-F", "c", "-f", str(dump_path), dbname,
            ],
            capture_output=True,
            text=True,
            timeout=180,
            env=_pg_env(password),
        )
    except subprocess.TimeoutExpired:
        return False, {"error": "Tiempo de espera agotado ejecutando pg_dump"}

    if result.returncode != 0:
        return False, {"error": (result.stderr or result.stdout).strip()[:1000]}

    sha256 = hashlib.sha256()
    with open(dump_path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            sha256.update(chunk)

    return True, {
        "size_bytes": dump_path.stat().st_size,
        "sha256_hash": sha256.hexdigest(),
        "storage_path": str(dump_path),
    }


def run_restore_database(
    host: str, port: str, admin_user: str, admin_password: str, source_dbname: str, dump_path: str,
    app_role: str | None = None,
) -> tuple[bool, dict]:
    if not DB_IDENTIFIER_RE.match(source_dbname):
        return False, {"error": "Nombre de base de datos inválido"}
    if app_role is not None and not DB_IDENTIFIER_RE.match(app_role):
        return False, {"error": "Rol de aplicación inválido"}
    if not Path(dump_path).is_file():
        return False, {"error": f"No se encontró el archivo de respaldo: {dump_path}"}

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    new_dbname = f"{source_dbname}_restore_{timestamp}"
    env = _pg_env(admin_password)

    try:
        create = subprocess.run(
            [_pg_tool("createdb"), "-h", host, "-p", str(port), "-U", admin_user, new_dbname],
            capture_output=True,
            text=True,
            timeout=60,
            env=env,
        )
        if create.returncode != 0:
            return False, {"error": (create.stderr or create.stdout).strip()[:1000]}

        restore = subprocess.run(
            [
                _pg_tool("pg_restore"),
                "-h", host, "-p", str(port), "-U", admin_user,
                "-d", new_dbname, "--no-owner", "--no-privileges", dump_path,
            ],
            capture_output=True,
            text=True,
            timeout=180,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return False, {"error": "Tiempo de espera agotado ejecutando pg_restore"}

    # pg_restore can exit non-zero on non-fatal warnings; the new DB existing with data is what matters.
    if restore.returncode != 0 and "error" in (restore.stderr or "").lower():
        return False, {"error": restore.stderr.strip()[:1000]}

    result = {"restored_to_path": new_dbname}
    if app_role:
        # pg_restore ran with --no-owner --no-privileges, so every object in the restored
        # DB is owned by admin_user (postgres) — the app's own least-privilege role can't
        # read any of it until this runs. admin_user is the superuser here, so this grant
        # essentially cannot fail; a failure is still non-fatal to the restore itself
        # (data is there and verifiable as postgres) but gets surfaced for visibility.
        grant_sql = (
            f'GRANT USAGE ON SCHEMA public TO "{app_role}"; '
            f'GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO "{app_role}"; '
            f'GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO "{app_role}";'
        )
        try:
            grant = subprocess.run(
                [
                    _pg_tool("psql"), "-h", host, "-p", str(port), "-U", admin_user,
                    "-d", new_dbname, "-v", "ON_ERROR_STOP=1", "-c", grant_sql,
                ],
                capture_output=True,
                text=True,
                timeout=30,
                env=env,
            )
            if grant.returncode != 0:
                result["grant_warning"] = (grant.stderr or grant.stdout).strip()[:500]
        except subprocess.TimeoutExpired:
            result["grant_warning"] = "Tiempo de espera agotado aplicando GRANT al rol de aplicación"

    return True, result


_io_state: dict = {"net": None, "disk": None, "disk_perdisk": None, "at": None}
_process_state: dict = {"next_at": 0.0, "top_cpu": [], "top_ram": [], "port_connections": [], "sampled_at": None}
_events_state: dict = {
    "next_at": 0.0,
    "watermarks": {name: 0 for name in CRITICAL_EVENT_LOGS},  # Windows: EventRecordID per log
    "cursor": None,  # Linux: opaque journalctl --after-cursor position
}


def _collect_io_rates() -> dict:
    """Current network/disk throughput as a delta since the last sample — the raw
    counters below in collect_metrics() are cumulative since boot and hard to read at a
    glance. nowrap=True avoids a bogus spike if a 32-bit counter wraps on a long-uptime
    box."""
    now = time.monotonic()
    net = psutil.net_io_counters(nowrap=True)
    disk = psutil.disk_io_counters(nowrap=True)
    # Per physical device, not per mount — psutil has no notion of "which device backs
    # this mountpoint" (that mapping gets genuinely unreliable with LVM/RAID), so this
    # stays keyed by whatever device name the OS itself reports, same as the SMART
    # table already does, rather than pretending a mount-level number we can't back up.
    try:
        disk_perdisk = psutil.disk_io_counters(perdisk=True, nowrap=True)
    except OSError:
        disk_perdisk = {}

    rates = {
        "net_sent_rate_mbps": None,
        "net_recv_rate_mbps": None,
        "disk_read_mbps": None,
        "disk_write_mbps": None,
    }
    disk_io: list[dict] = []
    prev_net, prev_disk, prev_at = _io_state["net"], _io_state["disk"], _io_state["at"]
    prev_perdisk = _io_state["disk_perdisk"] or {}
    if prev_at is not None:
        elapsed = max(now - prev_at, 0.001)
        rates["net_sent_rate_mbps"] = round(max(net.bytes_sent - prev_net.bytes_sent, 0) * 8 / 1_000_000 / elapsed, 2)
        rates["net_recv_rate_mbps"] = round(max(net.bytes_recv - prev_net.bytes_recv, 0) * 8 / 1_000_000 / elapsed, 2)
        if prev_disk is not None and disk is not None:
            rates["disk_read_mbps"] = round(max(disk.read_bytes - prev_disk.read_bytes, 0) / (1024**2) / elapsed, 2)
            rates["disk_write_mbps"] = round(max(disk.write_bytes - prev_disk.write_bytes, 0) / (1024**2) / elapsed, 2)

        for device, counters in disk_perdisk.items():
            prev_counters = prev_perdisk.get(device)
            if prev_counters is None:
                continue  # new device since last sample (rare) — needs one more cycle to have a delta
            disk_io.append(
                {
                    "device": device,
                    "read_mbps": round(max(counters.read_bytes - prev_counters.read_bytes, 0) / (1024**2) / elapsed, 2),
                    "write_mbps": round(max(counters.write_bytes - prev_counters.write_bytes, 0) / (1024**2) / elapsed, 2),
                }
            )

    _io_state["net"], _io_state["disk"], _io_state["disk_perdisk"], _io_state["at"] = net, disk, disk_perdisk, now
    rates["disk_io"] = disk_io
    return rates


def _collect_top_processes() -> tuple[list[dict], list[dict]]:
    """Top processes by CPU and by RAM as two separate lists — a CPU spike and a memory
    leak are different problems and can point at different processes. The first
    cpu_percent() sample per process is unreliable (same caveat as the system-wide one
    primed once in heartbeat_loop) but self-heals within one ~60s refresh cycle."""
    processes = []
    for proc in psutil.process_iter(attrs=["pid", "name", "cpu_percent", "memory_info"]):
        try:
            info = proc.info
            if info["memory_info"] is None:
                continue
            processes.append(
                {
                    "pid": info["pid"],
                    "name": info["name"],
                    "cpu_percent": round(info["cpu_percent"] or 0.0, 1),
                    "ram_mb": round(info["memory_info"].rss / (1024**2)),
                }
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    top_cpu = sorted(processes, key=lambda p: p["cpu_percent"], reverse=True)[:TOP_PROCESS_COUNT]
    top_ram = sorted(processes, key=lambda p: p["ram_mb"], reverse=True)[:TOP_PROCESS_COUNT]
    return top_cpu, top_ram


def _collect_port_connections() -> list[dict]:
    """Snapshot of established-connection counts per listening TCP port — not tied to
    any particular Service definition here (the agent doesn't know about those, that's
    a Core/DB concept); Core cross-references this against each Service.port when
    rendering. Same refresh cadence as processes (PROCESS_REFRESH_SECONDS) since
    enumerating connections has similar cost to enumerating processes."""
    try:
        connections = psutil.net_connections(kind="inet")
    except (psutil.AccessDenied, OSError):
        return []

    listening_ports: set[int] = set()
    established_by_port: dict[int, int] = {}
    for conn in connections:
        if conn.status == psutil.CONN_LISTEN and conn.laddr:
            listening_ports.add(conn.laddr.port)
        elif conn.status == psutil.CONN_ESTABLISHED and conn.laddr:
            established_by_port[conn.laddr.port] = established_by_port.get(conn.laddr.port, 0) + 1

    return [
        {"port": port, "connection_count": established_by_port.get(port, 0)}
        for port in sorted(listening_ports)
    ]


def _collect_critical_events() -> list[dict]:
    return _collect_critical_events_windows() if IS_WINDOWS else _collect_critical_events_linux()


def _collect_critical_events_linux() -> list[dict]:
    """New Level 1 (Crítico, syslog emerg/alert/crit) or 2 (Error, syslog err) journal
    entries since the last check. Uses journalctl -o json (built into every systemd
    Linux, including Oracle Linux) — no extra dependency. --after-cursor resumes exactly
    where the last poll left off; on the very first call (no cursor yet) we only take the
    50 most recent entries rather than replay the server's entire history. The journal's
    __SEQNUM is used as event_record_id (mirrors EventRecordID's role on Windows) purely
    as the dedup key — the cursor, not the seqnum, is what drives the actual query."""
    cursor = _events_state["cursor"]
    command = ["journalctl", "-p", "0..3", "-o", "json", "-q", "--no-pager"]
    command += [f"--after-cursor={cursor}"] if cursor else ["-n", "50"]

    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=20)
    except (subprocess.TimeoutExpired, OSError):
        return []
    if result.returncode != 0 or not result.stdout.strip():
        return []

    events: list[dict] = []
    last_cursor = cursor
    for line in result.stdout.strip().splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue

        try:
            seqnum = int(entry.get("__SEQNUM", 0))
        except (TypeError, ValueError):
            continue
        try:
            priority = int(entry.get("PRIORITY", 6))
        except (TypeError, ValueError):
            priority = 6
        level = 1 if priority <= 2 else 2  # emerg/alert/crit -> Crítico, err -> Error

        message = entry.get("MESSAGE")
        message = message if isinstance(message, str) else None
        provider = entry.get("SYSLOG_IDENTIFIER") or entry.get("_COMM")

        occurred_at = None
        try:
            realtime_us = int(entry.get("__REALTIME_TIMESTAMP", 0))
            if realtime_us:
                occurred_at = datetime.fromtimestamp(realtime_us / 1_000_000, tz=timezone.utc).isoformat()
        except (TypeError, ValueError):
            pass

        events.append(
            {
                "log_name": "journal",
                "event_record_id": seqnum,
                "level": level,
                "provider": provider,
                "event_id": None,
                "message": message,
                "occurred_at": occurred_at,
            }
        )
        last_cursor = entry.get("__CURSOR", last_cursor)

    _events_state["cursor"] = last_cursor
    return events


def _collect_critical_events_windows() -> list[dict]:
    """New System/Application Level 1 (Critical) or 2 (Error) events since the last
    check, per log. Uses wevtutil (built into Windows) + stdlib XML parsing — no
    pywin32/wmi dependency needed. /rd:false (chronological) matters: combined with a
    watermark filter, newest-first order could skip older events if a burst larger than
    /c:50 lands between polls. Watermark resets on agent restart (in-memory only), which
    can re-send a few already-seen events once — the backend dedupes on insert."""
    watermarks = _events_state["watermarks"]
    ns = {"e": "http://schemas.microsoft.com/win/2004/08/events/event"}
    events: list[dict] = []

    for log_name in CRITICAL_EVENT_LOGS:
        query = f"*[System[(Level=1 or Level=2) and (EventRecordID>{watermarks[log_name]})]]"
        try:
            result = subprocess.run(
                ["wevtutil", "qe", log_name, f"/q:{query}", "/c:50", "/rd:false", "/f:RenderedXml"],
                capture_output=True,
                text=True,
                timeout=20,
            )
        except (subprocess.TimeoutExpired, OSError):
            continue
        if result.returncode != 0 or not result.stdout.strip():
            continue

        for line in result.stdout.strip().splitlines():
            line = line.strip()
            if not line.startswith("<Event"):
                continue
            try:
                root = ET.fromstring(line)
            except ET.ParseError:
                continue
            system = root.find("e:System", ns)
            if system is None:
                continue
            try:
                record_id = int(system.findtext("e:EventRecordID", default="0", namespaces=ns))
            except ValueError:
                continue
            level = int(system.findtext("e:Level", default="0", namespaces=ns) or 0)
            provider_el = system.find("e:Provider", ns)
            provider = provider_el.get("Name") if provider_el is not None else None
            event_id_text = (system.findtext("e:EventID", default="", namespaces=ns) or "").strip()
            event_id = int(event_id_text) if event_id_text.isdigit() else None
            time_created = system.find("e:TimeCreated", ns)
            occurred_at = time_created.get("SystemTime") if time_created is not None else None
            rendering = root.find("e:RenderingInfo", ns)
            message = rendering.findtext("e:Message", default=None, namespaces=ns) if rendering is not None else None

            events.append(
                {
                    "log_name": log_name,
                    "event_record_id": record_id,
                    "level": level,
                    "provider": provider,
                    "event_id": event_id,
                    "message": message,
                    "occurred_at": occurred_at,
                }
            )
            watermarks[log_name] = max(watermarks[log_name], record_id)

    return events


def _detect_cpu_model() -> str | None:
    """A human-readable chip name — platform.processor() gives a real one on Windows but
    frequently just returns the bare architecture (e.g. "x86_64") on Linux, so there we
    read /proc/cpuinfo's "model name" line instead."""
    if IS_WINDOWS:
        return platform.processor() or None
    try:
        with open("/proc/cpuinfo", encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.lower().startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or None


_HOP_IP_RE = re.compile(r"\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b")
_HOP_MS_RE = re.compile(r"<?(\d+(?:\.\d+)?)\s*ms")


def _parse_ping_output(stdout: str, probes: int) -> tuple[str | None, float | None, float]:
    """Parses `ping`'s own text output for one hop's worth of probes — deliberately by
    shape (IP-address pattern, "N ms" pattern, and the blank line that both Windows'
    and Linux's ping put between the per-probe replies and the summary stats section),
    not by matching specific words, so this doesn't care whether the OS is running in
    Spanish or English."""
    lines = stdout.splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)  # Windows ping output starts with a blank line before the header
    if lines:
        lines.pop(0)  # drop the header line itself ("Haciendo ping a.../PING x.x.x.x...") —
        # it always names the FINAL target, which would otherwise get miscounted as an
        # extra reply on every intermediate hop (whose real replies carry a *different* IP)
    reply_lines: list[str] = []
    for line in lines:
        if not line.strip():
            break  # blank line = start of the summary stats section, stop here
        reply_lines.append(line)

    responder: str | None = None
    latencies: list[float] = []
    responded = 0
    for line in reply_lines:
        ip_match = _HOP_IP_RE.search(line)
        if ip_match is None:
            continue  # a timeout line for this probe ("Tiempo de espera agotado...", "Request timed out") — counts as loss
        responded += 1
        responder = ip_match.group(1)
        ms_match = _HOP_MS_RE.search(line)
        if ms_match:
            latencies.append(float(ms_match.group(1)))

    loss_percent = round(100 * (1 - responded / probes), 1) if probes else 0.0
    avg_latency_ms = round(sum(latencies) / len(latencies), 1) if latencies else None
    return responder, avg_latency_ms, loss_percent


def _probe_hop(target_ip: str, ttl: int, probes: int, timeout: float) -> tuple[str | None, float | None, float]:
    """One hop's worth of probing (`probes` pings at this TTL), via the OS's own `ping`
    — see NETWORK_PATH_ENABLED's history note above for why this shells out to a
    well-known system binary instead of this process opening raw ICMP sockets itself."""
    if IS_WINDOWS:
        command = ["ping", "-n", str(probes), "-i", str(ttl), "-w", str(int(timeout * 1000)), target_ip]
    else:
        command = ["ping", "-n", "-c", str(probes), "-t", str(ttl), "-W", str(max(1, math.ceil(timeout))), target_ip]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout * probes + 5)
    except (subprocess.TimeoutExpired, OSError):
        return None, None, 100.0
    return _parse_ping_output(result.stdout, probes)


def _traceroute(target_host: str) -> dict:
    """Multi-hop path probe via repeated calls to the OS's own `ping` with an
    increasing TTL (same technique traceroute/tracert use internally: each router
    along the path replies "Time Exceeded" until the destination itself finally
    replies) — see NETWORK_PATH_ENABLED's history note above for why this shells out
    rather than building ICMP packets in this process directly."""
    try:
        target_ip = socket.gethostbyname(target_host)
    except OSError:
        return {"target": target_host, "reachable": False, "hops": []}

    hops: list[dict] = []
    for ttl in range(1, TRACEROUTE_MAX_HOPS + 1):
        responder, avg_latency_ms, loss_percent = _probe_hop(
            target_ip, ttl, TRACEROUTE_PROBES_PER_HOP, TRACEROUTE_TIMEOUT_SECONDS
        )
        hops.append(
            {
                "hop_number": ttl,
                "address": responder,
                "avg_latency_ms": avg_latency_ms,
                "packet_loss_percent": loss_percent,
            }
        )
        if responder == target_ip:
            return {"target": target_host, "reachable": True, "hops": hops}

    return {"target": target_host, "reachable": False, "hops": hops}


_network_path_state: dict = {"result": None, "sent": True}


async def network_path_loop(core_target: str) -> None:
    """Independent task, own timer — see the NETWORK_PATH_INTERVAL_SECONDS comment
    above for why this doesn't live inside collect_metrics() like process/event
    sampling does.

    Raw-socket network code touches real, noisy production networks in ways that are
    hard to fully anticipate (malformed/truncated replies, unusual security appliances,
    etc.) — an uncaught exception here would silently end this task for the rest of the
    process's life (nothing awaits it), quietly turning off network diagnostics without
    otherwise affecting the agent. Catching and logging keeps one bad cycle from
    costing every cycle after it."""
    while True:
        try:
            result = await asyncio.to_thread(_traceroute, core_target)
            result["sampled_at"] = datetime.now(timezone.utc).isoformat()
            _network_path_state["result"] = result
            _network_path_state["sent"] = False
        except Exception as exc:  # noqa: BLE001 - see docstring
            print(f"[citi-agent] fallo en el sondeo de ruta de red (se reintentará): {exc}")
        await asyncio.sleep(NETWORK_PATH_INTERVAL_SECONDS)


def _parse_smart_device(name: str, data: dict) -> dict:
    """Normalizes one smartctl -a -j device into the shape sent to Core. Every field
    but `device` is best-effort — wearout in particular is often unavailable (older
    drives, HDDs with no wear concept, SATA SSDs whose vendor doesn't populate the
    usual attribute IDs); None there is an expected, common outcome, not a bug."""
    nvme_log = data.get("nvme_smart_health_information_log")
    disk_type = "nvme" if nvme_log is not None or (data.get("device") or {}).get("type") == "nvme" else "hdd_or_ssd"

    wearout_percent = None
    error_count = None
    if nvme_log is not None:
        used = nvme_log.get("percentage_used")
        if used is not None:
            wearout_percent = float(used)
        error_count = nvme_log.get("media_errors")
    else:
        for attr in (data.get("ata_smart_attributes") or {}).get("table") or []:
            attr_id = attr.get("id")
            # 177 = Wear_Leveling_Count, 233 = Media_Wearout_Indicator — both SSD-only
            # attributes, normalized 0-100 where higher means LESS worn, opposite of
            # our own 0-100 "percent worn" convention, hence the inversion.
            if attr_id in (177, 233) and wearout_percent is None and attr.get("value") is not None:
                wearout_percent = round(max(0.0, 100.0 - float(attr["value"])), 1)
            if attr_id == 5:  # Reallocated_Sector_Count — the closest thing to a universal HDD/SSD error signal
                raw = (attr.get("raw") or {}).get("value")
                if raw is not None:
                    error_count = int(raw)

    return {
        "device": name,
        "type": disk_type,
        "power_on_hours": (data.get("power_on_time") or {}).get("hours"),
        "smart_passed": (data.get("smart_status") or {}).get("passed"),
        "wearout_percent": wearout_percent,
        "temperature_c": (data.get("temperature") or {}).get("current"),
        "error_count": error_count,
    }


def _collect_smart_linux() -> dict:
    if shutil.which("smartctl") is None:
        return {"available": False, "disks": []}
    try:
        scan = subprocess.run(["smartctl", "--scan", "-j"], capture_output=True, text=True, timeout=15)
        scan_data = json.loads(scan.stdout or "{}")
    except (subprocess.TimeoutExpired, OSError, json.JSONDecodeError):
        return {"available": False, "disks": []}

    disks = []
    for device in scan_data.get("devices") or []:
        name = device.get("name")
        if not name:
            continue
        try:
            result = subprocess.run(["smartctl", "-a", "-j", name], capture_output=True, text=True, timeout=20)
            data = json.loads(result.stdout or "{}")
            disks.append(_parse_smart_device(name, data))
        except (subprocess.TimeoutExpired, OSError, json.JSONDecodeError, ValueError, TypeError):
            # One unreadable/oddly-shaped device shouldn't cost every other disk on
            # this same cycle — same "isolate the failure" reasoning as network_path.
            continue

    return {"available": True, "disks": disks}


_SMART_WINDOWS_SCRIPT = (
    "$ErrorActionPreference = 'SilentlyContinue'; "
    "Get-PhysicalDisk | ForEach-Object { "
    "$d = $_; $rel = $d | Get-StorageReliabilityCounter; "
    "[PSCustomObject]@{ DeviceId = $d.DeviceId; MediaType = [string]$d.MediaType; "
    "HealthStatus = [string]$d.HealthStatus; PowerOnHours = $rel.PowerOnHours; "
    "Temperature = $rel.Temperature; Wear = $rel.Wear; "
    "ReadErrors = $rel.ReadErrorsUncorrected; WriteErrors = $rel.WriteErrorsUncorrected } "
    "} | ConvertTo-Json -Compress"
)


def _collect_smart_windows() -> dict:
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", _SMART_WINDOWS_SCRIPT],
            capture_output=True, text=True, timeout=30,
        )
    except (subprocess.TimeoutExpired, OSError):
        return {"available": False, "disks": []}

    output = (result.stdout or "").strip()
    if not output:
        return {"available": False, "disks": []}
    try:
        parsed = json.loads(output)
    except json.JSONDecodeError:
        return {"available": False, "disks": []}

    # ConvertTo-Json emits a bare object (not a 1-element array) when the pipeline
    # only produced one result — a well-known PowerShell quirk, not a fluke.
    rows = parsed if isinstance(parsed, list) else [parsed]
    disks = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        media_type = (row.get("MediaType") or "").strip().lower()
        read_errors = row.get("ReadErrors")
        write_errors = row.get("WriteErrors")
        error_values = [v for v in (read_errors, write_errors) if v is not None]
        health = row.get("HealthStatus")
        disks.append(
            {
                "device": str(row.get("DeviceId", "?")),
                "type": media_type if media_type in ("hdd", "ssd") else "unknown",
                "power_on_hours": row.get("PowerOnHours"),
                "smart_passed": (health == "Healthy") if health else None,
                "wearout_percent": row.get("Wear"),
                "temperature_c": row.get("Temperature"),
                "error_count": sum(error_values) if error_values else None,
            }
        )
    return {"available": True, "disks": disks}


_smart_state: dict = {"result": None, "sent": True}


async def smart_loop() -> None:
    """Independent task, own (long) timer — see SMART_ENABLED's comment above."""
    while True:
        try:
            result = await asyncio.to_thread(_collect_smart_windows if IS_WINDOWS else _collect_smart_linux)
            result["sampled_at"] = datetime.now(timezone.utc).isoformat()
            _smart_state["result"] = result
            _smart_state["sent"] = False
        except Exception as exc:  # noqa: BLE001 - one bad cycle must not end this task forever
            print(f"[citi-agent] fallo en el sondeo de salud SMART (se reintentará): {exc}")
        await asyncio.sleep(SMART_CHECK_INTERVAL_SECONDS)


# Static-ish info (kernel, CPU model, agent version) is collected once and cached — no
# reason to redo this work on every heartbeat. Load average is the one field here that
# actually changes, so it's read fresh each time despite living in the same dict.
_system_info: dict = {
    "kernel_version": platform.release() or None,
    "cpu_model": _detect_cpu_model(),
    "agent_version": AGENT_VERSION,
}


def _collect_load_average() -> float | None:
    """1-minute load average — POSIX only (os.getloadavg), no Windows equivalent."""
    if IS_WINDOWS:
        return None
    try:
        return round(os.getloadavg()[0], 2)
    except OSError:
        return None


def collect_metrics() -> dict:
    """Point-in-time system metrics. Runs off the event loop thread (see heartbeat_loop)
    since disk_usage() can block on a slow/unresponsive drive."""
    disks = []
    for part in psutil.disk_partitions(all=False):
        if "cdrom" in part.opts or not part.fstype:
            continue
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except OSError:
            continue
        inode_total = None
        inode_used_percent = None
        if not IS_WINDOWS:
            # NTFS has no user-facing inode concept the way POSIX filesystems do
            # (Windows tooling doesn't expose an equivalent), so this stays None there
            # — os.statvfs itself doesn't exist on Windows and would raise otherwise.
            try:
                vfs = os.statvfs(part.mountpoint)
                if vfs.f_files > 0:
                    inode_total = vfs.f_files
                    inode_used_percent = round(100 * (1 - vfs.f_ffree / vfs.f_files), 1)
            except OSError:
                pass

        disks.append(
            {
                "mount": part.mountpoint,
                "total_gb": round(usage.total / (1024**3), 1),
                "free_gb": round(usage.free / (1024**3), 1),
                "percent_used": usage.percent,
                "inode_total": inode_total,
                "inode_used_percent": inode_used_percent,
            }
        )

    vmem = psutil.virtual_memory()
    net = psutil.net_io_counters()
    io_rates = _collect_io_rates()

    now = time.monotonic()
    if now >= _process_state["next_at"]:
        _process_state["top_cpu"], _process_state["top_ram"] = _collect_top_processes()
        _process_state["port_connections"] = _collect_port_connections()
        _process_state["sampled_at"] = datetime.now(timezone.utc).isoformat()
        _process_state["next_at"] = now + PROCESS_REFRESH_SECONDS

    critical_events: list[dict] = []
    if now >= _events_state["next_at"]:
        critical_events = _collect_critical_events()
        _events_state["next_at"] = now + EVENTS_REFRESH_SECONDS

    network_path = None
    if _network_path_state["result"] is not None and not _network_path_state["sent"]:
        network_path = _network_path_state["result"]
        _network_path_state["sent"] = True

    disk_health = None
    if _smart_state["result"] is not None and not _smart_state["sent"]:
        disk_health = _smart_state["result"]
        _smart_state["sent"] = True

    return {
        "cpu_percent": psutil.cpu_percent(interval=None),
        "ram_total_mb": round(vmem.total / (1024**2)),
        "ram_used_mb": round(vmem.used / (1024**2)),
        "ram_percent": vmem.percent,
        "disks": disks,
        "net_bytes_sent": net.bytes_sent,
        "net_bytes_recv": net.bytes_recv,
        "uptime_seconds": int(time.time() - psutil.boot_time()),
        **io_rates,
        "top_cpu_processes": _process_state["top_cpu"],
        "top_ram_processes": _process_state["top_ram"],
        "port_connections": _process_state["port_connections"],
        "processes_updated_at": _process_state["sampled_at"],
        "critical_events": critical_events,
        "network_path": network_path,
        "disk_health": disk_health,
        "load_average_1m": _collect_load_average(),
        **_system_info,
    }


async def heartbeat_loop(ws) -> None:
    # First cpu_percent() call always returns 0.0 (no prior sample to diff against);
    # prime it once so the first real heartbeat already carries a meaningful value.
    await asyncio.to_thread(psutil.cpu_percent, None)
    while True:
        await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)
        metrics = await asyncio.to_thread(collect_metrics)
        await ws.send(json.dumps({"type": "heartbeat", "metrics": metrics}))


def _apply_agent_update(version: str, expected_sha256: str, source: str) -> None:
    """Verifies and installs a new citi_agent.py, then ends the process so the service
    supervisor (nssm on Windows, systemd on Linux — both already configured to restart
    on any exit, clean or not) brings it back up running the new code.

    This ships to every server in the fleet automatically (see hello_ack's
    latest_agent_version check), so a broken push isn't a one-server problem — it would
    take down monitoring for everyone at once. Two safeguards against that before the
    file is ever applied: the candidate is run once as a subprocess in --selftest mode
    (imports the module and exits immediately, without connecting anywhere) so a
    NameError/ImportError/etc. anywhere at module level fails loudly here instead of in
    a crash-restart loop across the whole fleet; and the previous working copy is saved
    as citi_agent.py.bak first, so a bad version that somehow passes the self-test can
    still be restored by hand. Writing the candidate to a sibling temp file and
    os.replace()-ing over the original keeps the install itself atomic — a crash or
    power loss mid-write can never leave a half-written, unrunnable citi_agent.py on
    disk, since the original stays intact until the new file is fully flushed."""
    actual_sha256 = hashlib.sha256(source.encode("utf-8")).hexdigest()
    if actual_sha256 != expected_sha256:
        print(f"[citi-agent] actualizacion a {version} descartada: sha256 no coincide (posible transferencia corrupta)")
        return

    self_path = Path(__file__).resolve()
    tmp_path = self_path.with_suffix(".py.new")
    tmp_path.write_text(source, encoding="utf-8")

    try:
        check = subprocess.run(
            [sys.executable, str(tmp_path), "--selftest"],
            capture_output=True, text=True, timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"[citi-agent] actualizacion a {version} descartada: la autoprueba no se pudo ejecutar ({exc})")
        tmp_path.unlink(missing_ok=True)
        return
    if check.returncode != 0:
        print(
            f"[citi-agent] actualizacion a {version} descartada: la autoprueba fallo "
            f"(codigo {check.returncode}): {check.stderr[-500:]}"
        )
        tmp_path.unlink(missing_ok=True)
        return

    backup_path = self_path.with_suffix(".py.bak")
    try:
        backup_path.write_bytes(self_path.read_bytes())
    except OSError as exc:
        print(f"[citi-agent] no se pudo respaldar la version anterior ({exc}); continuando de todas formas")

    os.replace(tmp_path, self_path)
    print(f"[citi-agent] actualizado de {AGENT_VERSION} a {version} (respaldo en {backup_path.name}); reiniciando...")
    os._exit(0)


async def handle_connection(ws, core_target: str) -> None:
    allowlist: dict[str, str] = {}
    hb_task = asyncio.create_task(heartbeat_loop(ws))
    net_task = asyncio.create_task(network_path_loop(core_target)) if NETWORK_PATH_ENABLED else None
    smart_task = asyncio.create_task(smart_loop()) if SMART_ENABLED else None
    try:
        async for raw in ws:
            message = json.loads(raw)
            msg_type = message.get("type")

            if msg_type == "hello_ack":
                allowlist = {s["service_id"]: s["control_identifier"] for s in message["services"]}
                print(f"[citi-agent] servicios administrables: {list(allowlist.values())}")

                latest_version = message.get("latest_agent_version")
                if latest_version and latest_version != AGENT_VERSION:
                    print(f"[citi-agent] version {latest_version} disponible (actual: {AGENT_VERSION}); solicitando actualizacion")
                    await ws.send(json.dumps({"type": "request_agent_source"}))

            elif msg_type == "agent_source":
                _apply_agent_update(message["version"], message["sha256"], message["source"])

            elif msg_type == "command":
                service_id = message["service_id"]
                control_identifier = message["control_identifier"]
                action = message["action"]

                if allowlist.get(service_id) != control_identifier:
                    success, output = False, "Servicio no autorizado para este agente"
                else:
                    print(f"[citi-agent] ejecutando {action} sobre {control_identifier}")
                    success, output = run_service_command(control_identifier, action)
                    print(f"[citi-agent] resultado: {'OK' if success else 'FALLO'} - {output[:200]}")

                await ws.send(
                    json.dumps(
                        {
                            "type": "result",
                            "action_log_id": message["action_log_id"],
                            "status": "success" if success else "failed",
                            "output": output,
                        }
                    )
                )

            elif msg_type == "backup":
                print(f"[citi-agent] respaldando {message['source_path']}")
                success, result = await asyncio.to_thread(run_backup, message["source_path"], message["storage_path"])
                print(f"[citi-agent] resultado del respaldo: {'OK' if success else 'FALLO'} - {result}")
                await ws.send(
                    json.dumps(
                        {
                            "type": "backup_result",
                            "backup_run_id": message["backup_run_id"],
                            "status": "success" if success else "failed",
                            **result,
                        }
                    )
                )

            elif msg_type == "restore":
                print(f"[citi-agent] restaurando {message['zip_path']} -> {message['target_path']}")
                success, result = await asyncio.to_thread(run_restore, message["zip_path"], message["target_path"])
                print(f"[citi-agent] resultado de la restauración: {'OK' if success else 'FALLO'} - {result}")
                await ws.send(
                    json.dumps(
                        {
                            "type": "restore_result",
                            "restore_id": message["restore_id"],
                            "status": "success" if success else "failed",
                            **result,
                        }
                    )
                )

            elif msg_type == "backup_database":
                print(f"[citi-agent] respaldando base de datos {message['dbname']}")
                success, result = await asyncio.to_thread(
                    run_backup_database,
                    message["host"],
                    message["port"],
                    message["dbname"],
                    message["user"],
                    message["password"],
                    message["storage_path"],
                )
                print(f"[citi-agent] resultado del respaldo de BD: {'OK' if success else 'FALLO'} - {result}")
                await ws.send(
                    json.dumps(
                        {
                            "type": "backup_result",
                            "backup_run_id": message["backup_run_id"],
                            "status": "success" if success else "failed",
                            **result,
                        }
                    )
                )

            elif msg_type == "git_status":
                print(f"[citi-agent] consultando estado de git en {message['repo_path']}")
                result = await asyncio.to_thread(
                    get_git_status, message["repo_path"], message["repo_url"], message["branch"], message["token"]
                )
                status_summary = result.get("error") or f"{result.get('commits_behind')} commits atrás"
                print(f"[citi-agent] git status: {status_summary}")
                await ws.send(json.dumps({"type": "git_status_result", "request_id": message["request_id"], **result}))

            elif msg_type == "deploy":
                print(f"[citi-agent] desplegando {message['repo_path']} (target={message.get('target_commit') or 'latest'})")
                success, result = await asyncio.to_thread(
                    run_deploy,
                    message["repo_path"],
                    message["repo_url"],
                    message["branch"],
                    message.get("target_commit"),
                    message.get("build_command"),
                    message["token"],
                )
                print(f"[citi-agent] resultado del despliegue: {'OK' if success else 'FALLO'} - {result.get('error') or result.get('new_commit')}")
                await ws.send(
                    json.dumps(
                        {
                            "type": "deploy_result",
                            "deployment_id": message["deployment_id"],
                            "status": "success" if success else "failed",
                            **result,
                        }
                    )
                )

            elif msg_type == "restore_database":
                print(f"[citi-agent] restaurando base de datos {message['source_dbname']} desde {message['dump_path']}")
                success, result = await asyncio.to_thread(
                    run_restore_database,
                    message["host"],
                    message["port"],
                    message["admin_user"],
                    message["admin_password"],
                    message["source_dbname"],
                    message["dump_path"],
                    message.get("app_role"),
                )
                print(f"[citi-agent] resultado de la restauración de BD: {'OK' if success else 'FALLO'} - {result}")
                await ws.send(
                    json.dumps(
                        {
                            "type": "restore_result",
                            "restore_id": message["restore_id"],
                            "status": "success" if success else "failed",
                            **result,
                        }
                    )
                )

            elif msg_type == "http_check":
                print(f"[citi-agent] chequeo sintético: {message['url']}")
                result = await asyncio.to_thread(run_http_check, message["url"])
                print(f"[citi-agent] resultado del chequeo: {'OK' if result['success'] else 'FALLO'} - {result.get('error') or result['status_code']}")
                await ws.send(json.dumps({"type": "http_check_result", "check_id": message["check_id"], **result}))
    finally:
        hb_task.cancel()
        if net_task is not None:
            net_task.cancel()
        if smart_task is not None:
            smart_task.cancel()


async def main() -> None:
    config = load_config()
    ws_url = build_ws_url(config)
    core_target = _resolve_core_target(config["core_url"])

    while True:
        try:
            print(f"[citi-agent] conectando a {config['core_url']} ...")
            async with websockets.connect(ws_url) as ws:
                print("[citi-agent] conectado a CITI Core")
                await handle_connection(ws, core_target)
        except (websockets.exceptions.ConnectionClosed, OSError) as exc:
            print(f"[citi-agent] desconectado ({exc}); reintentando en {RECONNECT_DELAY_SECONDS}s...")
        await asyncio.sleep(RECONNECT_DELAY_SECONDS)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        # Reaching this line means the module above imported and its module-level code
        # (constants, _system_info's platform/psutil probing, etc.) ran without raising —
        # that's the entire check. Used by _apply_agent_update to validate a downloaded
        # update before installing it; never connects anywhere.
        sys.exit(0)
    asyncio.run(main())
