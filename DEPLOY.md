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

## Si el host único se cae

Todo corre en una sola máquina (Postgres, backend, agent, proxy, observabilidad) — no hay
redundancia. Ver `backups/` para los dumps de las bases de datos (respaldados automáticamente
según `schedule_cron` en cada `BackupJob`, ver Administración → Sedes/Sistemas → Backups).
Para reconstruir desde cero: reinstalar los servicios NSSM (ver `tools/nssm-2.24/`), restaurar
la última base de datos desde `backups/`, y correr `alembic upgrade head`.
