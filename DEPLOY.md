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
