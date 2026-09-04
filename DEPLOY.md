# Despliegue

## Servicios (NSSM, todos en 172.20.1.51)

| Servicio | Qué hace | Puerto |
|---|---|---|
| `CitiBackend` | API FastAPI (uvicorn) | 8010 (HTTP, solo interno) |
| `CitiProxy` | Caddy — TLS + sirve `frontend/dist/` + reverse proxy a `/api/v1/*` | 443 (HTTPS, público) / 80 (redirect) |
| `CitiFrontend` | Vite dev server — **solo para desarrollo**, no lo usan los técnicos | 5190 (HTTP) |
| `CitiAgent`, `CitiAlloy`, `CitiGrafana`, `CitiLoki`, `CitiPrometheus` | Observabilidad / agente propio de este servidor | — |

Los técnicos usan **`https://172.20.1.51`** (puerto 443, vía `CitiProxy`). El certificado es
self-signed (`certs/cert.pem` / `certs/key.pem`) — el navegador muestra una advertencia la
primera vez en cada equipo; "Avanzado" → "Continuar" para aceptarlo. `http://172.20.1.51:5190`
sigue funcionando igual que siempre para desarrollo activo (HMR de Vite), no está pensado para
que lo usen técnicos.

## Después de un cambio en el backend

```
Restart-Service -Name CitiBackend
```

## Después de un cambio en el frontend

A diferencia de antes: un cambio en `frontend/src` **no se refleja solo** en
`https://172.20.1.51` — hay que reconstruir el bundle de producción y Caddy lo sirve
directo desde disco (no hace falta reiniciar `CitiProxy`, solo regenerar `dist/`):

```
cd frontend
npm run build
```

(`npm run dev` en `:5190` sigue actualizándose solo con HMR, sin este paso — ese es el flujo
de desarrollo normal, este paso solo aplica para que el cambio llegue a los técnicos).

## Backups: qué está probado

Los respaldos de base de datos ahora sí corren solos si el `BackupJob` tiene `schedule_cron`
configurado (antes del 2026-09-02 el campo existía pero nada lo leía — ver el commit "Actually
schedule backups"). El botón "Restaurar" (`BackupsSection.tsx` → `POST /backup-runs/{id}/restore`)
**restaura a una base nueva con timestamp** (`{nombre}_restore_{fecha}`), nunca sobrescribe la
original — confirmado leyendo `agent/citi_agent.py:run_restore_database` (usa `createdb` +
`pg_restore` a un nombre nuevo) y con un drill real:

- 2026-09-02: respaldo manual de `citi_platform` (29MB) → restaurado a
  `citi_platform_restore_20260902T203128Z` → verificado con conteos de filas reales (24
  usuarios, 55 servidores, 26 sedes, coincide con producción) → base temporal eliminada
  después de verificar.

**Gap encontrado, no resuelto todavía**: la base restaurada solo es legible con el usuario
`postgres` (superusuario) — `pg_restore` corre con `--no-owner --no-privileges`, así que los
GRANT del rol `citi_app` (el que usa la app normalmente) no se aplican a la copia restaurada.
Para usar de verdad una restauración en un escenario real (no solo verificarla), hay que
correr `GRANT ALL ON ALL TABLES IN SCHEMA public TO citi_app;` (y `SEQUENCES`) en la base
nueva antes de apuntar la app ahí.

## Si el host único se cae

Todo corre en una sola máquina (Postgres, backend, agent, proxy, observabilidad) — no hay
redundancia. Runbook de recuperación:

1. Reinstalar los servicios NSSM (ver `tools/nssm-2.24/` y los comandos `nssm install`/`nssm set`
   usados para `CitiBackend`/`CitiProxy` — no hay un script que los reproduzca automáticamente
   todavía, hay que rearmarlos a mano siguiendo el patrón de los existentes).
2. Restaurar Postgres desde el dump más reciente de `backups/citi-platform-db/` (`pg_restore`
   a una base llamada `citi_platform`, o al nombre que tenga `DATABASE_URL` en `backend/.env`).
3. Aplicar los GRANT de `citi_app` (ver gap arriba) y correr `alembic upgrade head` por si el
   dump es de antes de la última migración.
4. Restaurar `certs/` (el cert self-signed no está en git — regenerar con
   `certs/generate_cert.py` si no hay copia, aunque eso invalida el cert que los técnicos ya
   confiaron en su navegador).
5. Arrancar `CitiBackend` → `CitiProxy` → confirmar `https://<host>/health` responde antes de
   avisar a los técnicos.

## Migración de `postgresql-x64-16` de `pg_ctl runservice` a NSSM (2026-09-04)

**Por qué**: el 2026-09-01 y el 2026-09-04 Windows SCM marcó `postgresql-x64-16` como "detenido"
mientras el proceso real (`postgres.exe`, postmaster) seguía vivo y aceptando conexiones —
confirmado con el log propio de Postgres (`FATAL: el archivo de bloqueo «postmaster.pid» ya
existe... ¿Hay otro postmaster (PID 4796) en ejecución?`, es decir: SCM intentó re-arrancar el
servicio como parte de resolver una dependencia — de `SistemaPermisosBackend` el 09-04, de varios
servicios dependientes el 09-01 — y Postgres correctamente rechazó abrir un segundo postmaster).
Se descartó reinicio del host, política de recuperación de Windows, tarea programada, y acción
disparada desde CITI Platform (`service_action_logs` no tiene ningún registro para este servicio).
La causa más probable es una falla conocida de `pg_ctl runservice` como wrapper de SCM: reporta su
propio estado a Windows en un hilo separado del postmaster real, y ese reporte puede desincronizarse
sin dejar rastro hasta que algo lo expone. El resto del stack (`CitiBackend`, `CitiProxy`, etc.) ya
usa NSSM, que ata el estado de SCM directamente al handle del proceso real — no puede reportar
"detenido" mientras el proceso sigue vivo.

**Config original (capturada con `sc qc postgresql-x64-16` antes de tocar nada, para el rollback)**:

```
NOMBRE_RUTA_BINARIO: "C:\Program Files\PostgreSQL\16\bin\pg_ctl.exe" runservice -N "postgresql-x64-16" -D "C:\Program Files\PostgreSQL\16\data" -w
TIPO_INICIO        : AUTO_START
DEPENDENCIAS       : RPCSS
NOMBRE_INICIO_SERVICIO: NT AUTHORITY\NetworkService
NOMBRE_MOSTRAR     : postgresql-x64-16 - PostgreSQL Server 16
```

### Plan de corte (mismo nombre de servicio, para no romper `ServicesDependedOn` de los
servicios que dependen de él — `SistemaPermisosBackend`, backend de Celebraciones, HelpDesk, etc.)

```powershell
# 1. Parada limpia (mismo método usado el 09-04 para el incidente en vivo)
& "C:\Program Files\PostgreSQL\16\bin\pg_ctl.exe" stop -D "C:\Program Files\PostgreSQL\16\data" -m fast -w

# 2. Quitar el registro SCM viejo (pg_ctl runservice) — no toca datos
sc.exe delete postgresql-x64-16

# 3. Registrar el nuevo servicio NSSM apuntando directo a postgres.exe (no a pg_ctl)
$nssm = "E:\PROGRAMACION\Citi-Platform\tools\nssm-2.24\win64\nssm.exe"
& $nssm install postgresql-x64-16 "C:\Program Files\PostgreSQL\16\bin\postgres.exe" -D "C:\Program Files\PostgreSQL\16\data"
& $nssm set postgresql-x64-16 DisplayName "postgresql-x64-16 - PostgreSQL Server 16"
& $nssm set postgresql-x64-16 Start SERVICE_AUTO_START
& $nssm set postgresql-x64-16 AppDirectory "C:\Program Files\PostgreSQL\16\bin"
# OJO: AppParameters con la ruta completa entre comillas ("-D `"C:\Program Files\...`"") no
# sobrevive el paso por PowerShell -> nssm -> CreateProcess: las comillas se pierden y postgres
# recibe "Files\PostgreSQL\16\data" como argumento suelto ("argumento no válido"). Usar la ruta
# corta 8.3 (sin espacios) evita el problema por completo — obtenerla con:
#   (New-Object -ComObject Scripting.FileSystemObject).GetFolder("C:\Program Files\PostgreSQL\16\data").ShortPath
& $nssm set postgresql-x64-16 AppParameters "-D C:\PROGRA~1\POSTGR~1\16\data"
# Timeout generoso para el apagado (Ctrl+C -> postmaster hace shutdown "fast"); el default de
# NSSM (1.5s) es muy corto para checkpoint bajo carga real.
& $nssm set postgresql-x64-16 AppStopMethodConsole 30000
# Captura stdout/stderr — sin esto, cualquier error de postgres.exe ANTES de que arranque su
# propio logging_collector se pierde en silencio (así se diagnosticó el problema de la ruta).
& $nssm set postgresql-x64-16 AppStdout "C:\Program Files\PostgreSQL\16\data\log\nssm-stdout.log"
& $nssm set postgresql-x64-16 AppStderr "C:\Program Files\PostgreSQL\16\data\log\nssm-stderr.log"
# OJO: "password= """ (vacío) hace que sc.exe falle silenciosamente y muestre el USO en vez
# de aplicar el cambio — para una cuenta virtual (NT AUTHORITY\NetworkService) omitir password= por completo.
sc.exe config postgresql-x64-16 obj= "NT AUTHORITY\NetworkService"
sc.exe config postgresql-x64-16 depend= RPCSS

# 4. Arrancar y verificar
Start-Service postgresql-x64-16
Get-Service postgresql-x64-16   # esperado: Running
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -h localhost -U postgres -c "SELECT 1;"

# 5. CRÍTICO: probar el apagado controlado ANTES de darlo por bueno — confirmar en
#    data/log/postgresql-*.log que dice algo como "recibida solicitud de apagado rápido" /
#    "el sistema de base de datos está apagado" (apagado limpio), no un mensaje de recuperación
#    de fallo en el arranque siguiente (que indicaría que NSSM lo mató en vez de pedirle que
#    parara).
Stop-Service postgresql-x64-16
Start-Service postgresql-x64-16
```

### Rollback

Si el paso 5 muestra un apagado sucio (o cualquier otra cosa sale mal):

```powershell
# Si postgres.exe sigue vivo pero el servicio NSSM ya no responde, forzar y limpiar el lock
Get-Process postgres -ErrorAction SilentlyContinue | Stop-Process -Force
Remove-Item "C:\Program Files\PostgreSQL\16\data\postmaster.pid" -ErrorAction SilentlyContinue

& $nssm remove postgresql-x64-16 confirm

sc.exe create postgresql-x64-16 `
  binPath= "\"C:\Program Files\PostgreSQL\16\bin\pg_ctl.exe\" runservice -N \"postgresql-x64-16\" -D \"C:\Program Files\PostgreSQL\16\data\" -w" `
  start= auto obj= "NT AUTHORITY\NetworkService" depend= RPCSS `
  DisplayName= "postgresql-x64-16 - PostgreSQL Server 16"

Start-Service postgresql-x64-16
Get-Service postgresql-x64-16   # esperado: Running
```

**Nota**: si el rollback fuerza un `Stop-Process`, la próxima vez que arranque Postgres hará
recuperación de fallo (WAL replay) — normal, no es corrupción, solo tarda un poco más en aceptar
conexiones.

### Estado: aplicado y validado en producción (2026-09-04)

Migración ejecutada. Verificado con evidencia real, no solo "arrancó":

- El log de Postgres mostró un `checkpoint completo` (1094 búfers escritos, WAL sincronizado)
  seguido de `el sistema de bases de datos está apagado` al probar `Stop-Service` — apagado
  limpio real, no un `TerminateProcess`.
- Tras el reinicio, `Sistema de Permisos - Backend` reportó `db.status: "up"` end-to-end.
- `Técnico de Sede` ya no tiene `services.manage` (ver más abajo), así que ningún técnico puede
  repetir el patrón que originó el incidente del 09-04 (`Start-Service` manual sobre servicios
  dependientes) — solo Administrador y Operador pueden.

Los `nssm-stdout.log` / `nssm-stderr.log` en `data/log/` quedan vacíos en operación normal
(logging_collector de Postgres se encarga de todo); solo tendrán contenido si `postgres.exe`
falla antes de inicializar su propio logging — revisarlos primero si el servicio no arranca.
