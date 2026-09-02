# CITI Platform — Arquitectura General

Centro Inteligente de Tecnologías de la Información — Corte Superior de Justicia de Lima

Este documento traduce la visión de `analisis.txt` en una arquitectura técnica concreta y un roadmap por fases. Es un documento vivo: se actualiza a medida que el proyecto evoluciona.

---

## 1. Principio rector

CITI **no reemplaza** los sistemas existentes. Es una **capa de control y observabilidad** sobre sistemas que mantienen su independencia total (su propia BD, backend, frontend, config, logs, backups). CITI orquesta; no absorbe.

Esto implica una decisión de diseño clave: **no reinventar lo que ya existe como software libre maduro**. CITI se apoya en:

| Necesidad | Herramienta OSS | Rol de CITI |
|---|---|---|
| Métricas de servidor/proceso | Prometheus + Node Exporter | Consumir, correlacionar, mostrar en un solo dashboard |
| Visualización de métricas | Grafana (embebido o enlazado) | Integrar paneles dentro del portal |
| Logs centralizados | Loki + Promtail | Unificar vista de logs de todos los sistemas |
| Gestión de servicios OS | systemd (Linux) / SCM+NSSM (Windows) / PM2 | El Agente CITI los controla, no los sustituye |
| Contenedores (si existen) | Docker / Docker Compose | El Agente puede detectar y controlar contenedores vía Docker API |

CITI construye código propio donde **no existe** una pieza OSS que resuelva el problema con la semántica institucional que se necesita: el **registro de sistemas**, el **Agente CITI**, el **control plane**, el **RBAC institucional**, el **centro de respaldos con verificación**, el **asistente de IA institucional**.

---

## 2. Arquitectura de alto nivel

```
                         ┌───────────────────────────────┐
                         │        CITI Frontend           │
                         │  React + TS + Vite + shadcn/ui │
                         └───────────────┬─────────────────┘
                                         │ HTTPS / WebSocket
                         ┌───────────────▼─────────────────┐
                         │         CITI Core API            │
                         │   FastAPI + SQLAlchemy + Celery  │
                         │  (Auth/RBAC, Registro, Orquesta) │
                         └───┬─────────────┬───────────┬────┘
                             │             │           │
                    ┌────────▼───┐  ┌──────▼─────┐ ┌───▼────────┐
                    │ PostgreSQL │  │   Redis    │ │ Prometheus │
                    │ (metadata) │  │(cache/cola)│ │  + Loki    │
                    └────────────┘  └────────────┘ └───┬────────┘
                                                        │ scrape/push
        ┌───────────────────────────┬───────────────────┼───────────────────────────┐
        │                           │                   │                           │
┌───────▼────────┐         ┌────────▼───────┐   ┌────────▼───────┐         ┌─────────▼───────┐
│  Servidor 1     │         │  Servidor 2    │   │  Servidor 3    │         │  Servidor N      │
│  CITI Agent     │         │  CITI Agent    │   │  CITI Agent    │   ...   │  CITI Agent      │
│  ├ Sistema A    │         │  ├ Sistema B   │   │  ├ Sistema C   │         │  ├ ...           │
│  │ (FastAPI+PG) │         │  │ (Node+PG)   │   │  │ (.NET+SQL)  │         │  │                │
│  └ Node Exporter│         │  └ Node Exporter│  │  └ Node Exporter│        │  └ Node Exporter │
└─────────────────┘         └────────────────┘   └────────────────┘         └──────────────────┘
```

**CITI Core** es el único punto donde vive lógica de negocio institucional (registro, permisos, auditoría, orquestación de acciones). **CITI Agent** es el único componente que toca los sistemas gestionados directamente.

---

## 3. CITI Agent — diseño

El Agente es la pieza más crítica de seguridad y la que justifica desarrollo propio.

- **Despliegue**: un binario/servicio ligero por servidor (Windows Service o systemd unit), escrito en Python o Go (Go recomendado para binario único sin runtime, más fácil de distribuir en Windows Server).
- **Enrolamiento**: el agente se registra contra CITI Core con un token de un solo uso emitido desde el portal; recibe un certificado cliente (mTLS) para todas las comunicaciones posteriores.
- **Canal de comunicación**: WebSocket persistente (agente → Core) para métricas/logs en tiempo real y para recibir comandos, evitando abrir puertos entrantes en los servidores gestionados (los servidores institucionales suelen estar detrás de firewalls restrictivos — el agente inicia la conexión saliente).
- **Modelo de capacidades declarado**: cada agente reporta qué puede controlar en ese servidor (systemd units, Windows services, procesos PM2, contenedores Docker) — CITI Core arma el catálogo de servicios controlables automáticamente.
- **Ejecución de comandos**: **allowlist estricta** por servicio — el agente nunca ejecuta comandos arbitrarios; solo un conjunto cerrado de operaciones parametrizadas (start/stop/restart/status/tail-log/backup/run-script-registrado). Cualquier comando nuevo requiere agregarlo al catálogo del agente, no se acepta shell libre desde el Core.
- **Métricas**: expone/reenvía datos vía Node Exporter (estándar Prometheus) — no reinventa la recolección de CPU/RAM/disco.
- **Logs**: Promtail (o equivalente embebido) tailea los logs registrados por cada sistema y los envía a Loki.

---

## 4. Modelo de datos (núcleo)

Entidades principales en PostgreSQL (CITI Core):

- **Site** — sede institucional (para escalabilidad multi-sede)
- **Server** — host físico/VM, SO, agente asociado, estado de enrolamiento
- **System** (activo tecnológico) — ej. "HelpDesk": nombre, descripción, criticidad, propietario/responsable, repo Git, documentación asociada
- **Service** — unidad controlable dentro de un System (frontend, backend, DB, redis, nginx, servicio Windows, cron): tipo, servidor donde corre, comando de control, puerto, estado actual
- **Environment/Config** — variables ENV, secretos (cifrados), puertos, rutas — versionado
- **Backup** — job, tipo, ruta, hash, tamaño, resultado, servicio asociado
- **Deployment/Version** — historial de versiones, notas de cambio, commit, autor, estado (activo/rollback disponible)
- **AlertRule / AlertEvent** — condiciones y disparos
- **User / Role / Permission** — RBAC con scope por System (un operador puede tener permisos solo sobre ciertos sistemas)
- **AuditLog** — inmutable, append-only, registra toda acción sensible (quién, qué, cuándo, desde dónde)
- **Document** — manuales, diagramas, adjuntos, vinculados a un System

Este modelo es la base de datos propia de CITI (separada de las BD de cada sistema gestionado).

---

## 5. Seguridad

- **AuthN**: JWT de corta duración + refresh token; 2FA obligatorio para roles administrativos.
- **AuthZ**: RBAC con scope granular (rol × sistema), no solo roles globales.
- **Transporte**: HTTPS en frontend↔Core; mTLS en Agent↔Core.
- **Secretos**: cifrados en reposo (pgcrypto o cifrado a nivel de aplicación con clave gestionada fuera de la BD); nunca se muestran en claro salvo a roles autorizados, y su acceso queda auditado.
- **Auditoría**: log inmutable de toda acción de control (start/stop/restart, cambio de config, restauración de backup, ejecución de comando).
- **Allowlist de comandos** en el agente (ver §3) como control de defensa en profundidad — el Core comprometido no puede convertirse en RCE arbitrario sobre los servidores.

---

## 6. Módulos funcionales → mapeo de `analisis.txt`

| Módulo | Componente técnico |
|---|---|
| Dashboard Ejecutivo | Vistas agregadas sobre Prometheus + tabla `Service`/`System` |
| Centro de Aplicaciones | CRUD de `System` + ficha técnica |
| Control de Servicios | Comandos vía Agente sobre `Service` (switches) |
| Gestión de Infraestructura | CRUD de `Server`/dispositivos de red + estado vía agente/SNMP |
| Centro de Configuración | `Environment/Config` versionado y cifrado |
| Gestión de Versiones | `Deployment/Version` + integración Git |
| Centro de Respaldos | Jobs de `Backup` ejecutados por el Agente, con hash y restauración |
| Monitoreo | Proxy/embed de Prometheus+Grafana |
| Centro de Logs | Proxy/embed de Loki, con filtros propios |
| Gestión Documental | `Document` + almacenamiento de archivos |
| Inventario Tecnológico | Vista consolidada de `Server`+`System`+licencias |
| Integración Git | Webhooks + API de Git (GitLab/Gitea/GitHub) |
| Centro de Despliegues | Orquestación: pull → build → backup → restart, con rollback |
| Notificaciones | Adaptadores: SMTP, Telegram Bot API, Teams webhook |
| IA Institucional | Fase posterior — RAG sobre `Document`+`AuditLog`+`Backup`+métricas, con tool-calling de solo lectura hacia el Agente |

---

## 7. Roadmap por fases

No se construye todo a la vez. Cada fase entrega valor usable y sienta la base de la siguiente.

**Fase 0 — Fundación (Core + Registro)**
Modelo de datos base, Auth/RBAC, shell de frontend, API CRUD de `System`/`Server`/`Service` (registro manual, sin agente todavía). Objetivo: tener el "mapa" de todos los sistemas institucionales en un solo lugar.

**Fase 1 — Agente + Control de Servicios (implementado 2026-07-26)**
CITI Agent en Python (`agent/citi_agent.py`), enrolamiento por token de un solo uso (`POST /agents/servers/{id}/enroll-token` → `POST /agents/enroll` → credencial de agente vía JWT de larga duración), conexión WebSocket persistente y saliente hacia `/api/v1/agents/ws` (sin puertos entrantes en el servidor gestionado). Al conectar, Core le envía al Agente la allowlist exacta de servicios que puede controlar en ese servidor (`service_id` → `control_identifier`); el Agente rechaza cualquier comando fuera de esa lista, incluso si Core estuviera comprometido. Para `control_strategy: windows_service`, el Agente ejecuta `Start-Service`/`Stop-Service`/`Restart-Service` de PowerShell — no hace falta NSSM en tiempo de control, solo se usó NSSM para *registrar* los servicios inicialmente. `POST /services/{id}/actions` ahora despacha el comando real al Agente conectado (vía un hub en memoria) y espera el resultado con timeout de 20s antes de responder. Probado de extremo a extremo con un restart real sobre Sistema de Celebraciones.

**Fase 2 — Monitoreo y Logs (implementado 2026-07-26)**
Prometheus (`:9090`), windows_exporter (`:9182`), Grafana (`:3000`, admin/CitiGrafana2026!), Loki (`:3100`) y Grafana Alloy instalados como servicios NSSM/nativos en `E:\PROGRAMACION\Citi-Platform\observability\`. Grafana provisiona automáticamente los datasources de Prometheus y Loki, más un dashboard "Windows Exporter Node" en la carpeta "CITI Platform". Alloy reemplaza a Promtail (descontinuado) — lee `E:\PROGRAMACION\Citi-Platform\observability\alloy\config.alloy` y tailea los logs stdout/stderr de cada servicio NSSM (`local.file_match` con un path explícito por servicio/stream), enviándolos a Loki vía `loki.write`. Cualquier sistema nuevo que se agregue debe sumar sus rutas de log a ese archivo.

**Fase 3 — Backups (completa 2026-07-28: archivos + base de datos)**
`BackupJob`/`BackupRun`/`RestoreOperation` con dispatch-al-Agente igual que el control de servicios.
- *Archivos*: el Agente comprime la carpeta de origen (excluyendo `node_modules`/`venv`/`.git`/etc.), calcula SHA256; restaurar extrae a `<origen>/restored/<timestamp>/` — nunca sobrescribe el origen en vivo.
- *Base de datos*: nuevo módulo `app/api/v1/config.py` (`ConfigEntry` cifrado con Fernet, valores secretos siempre enmascarados en las respuestas de la API) guarda las credenciales de conexión (`DB_HOST/PORT/NAME/USER/PASSWORD`) por servicio. El Agente ejecuta `pg_dump`/`pg_restore`/`createdb` reales (binarios de `C:\Program Files\PostgreSQL\16\bin`). Restaurar crea una base de datos **nueva** (`<original>_restore_<timestamp>`) en vez de sobrescribir la original — mismo principio de "nunca destructivo por defecto" que los archivos.
- Las 4 bases de datos reales (`HelpDeskLima`, `helpdesk_test`, `permisosbd`, `celebraciones_db`) están registradas como servicios `type=database` con `control_strategy=windows_service` / `control_identifier=postgresql-x64-16` (la instancia compartida) — la UI oculta los botones start/stop/restart para este tipo de servicio, porque detenerlo afectaría a todos los sistemas del servidor a la vez.
- Probado de extremo a extremo: backup+restore real de archivos (Celebraciones) y backup+restore real de base de datos (helpdesk_test, 102 tablas verificadas idénticas entre original y restaurada). Backups reales ya corridos para los 3 sistemas de producción.

**Fase 4 — Configuración, Versiones y Despliegues (completa 2026-07-30)**
Centro de Configuración: UI sobre el `ConfigEntry` cifrado de Fase 3 — variables por servicio, secretos enmascarados, historial de cambios. Gestión de Versiones: registro de versiones por sistema, la más nueva "active", la anterior "deprecated".

Centro de Despliegues: `System.repo_url/default_branch/repo_local_path/deploy_build_command` + un `PlatformSecret` cifrado (`GITHUB_PAT`, fine-grained, solo lectura, limitado a los 4 repos) usado por el Agente para autenticar `git fetch` sin nunca escribir el token a disco (se inyecta solo en la URL de un `fetch` puntual, no se persiste en `.git/config`). Flujo:
1. `POST /systems/{id}/deploy/check` — el Agente hace `fetch` + compara commits, reporta si el árbol está "sucio" (cambios sin confirmar) y cuántos commits de diferencia hay. Es de solo lectura.
2. `POST /systems/{id}/deploy` — **rechaza el despliegue si el árbol está sucio** (verificado dos veces: en el check y de nuevo justo antes de tocar el repo, por si algo cambió en el medio). Si está limpio: fetch + `checkout <rama>` + `merge --ff-only` + comando de build opcional + reinicio de todos los servicios no-BD del sistema + registro automático de una nueva versión activa.
3. `POST /systems/{id}/deploy/rollback/{version_id}` — mismo flujo pero con `git checkout --detach <commit>` en vez de fast-forward; vuelve a dejar el repo en la rama correcta en el siguiente deploy normal.
Probado de extremo a extremo en el ambiente de pruebas de HelpDesk: commit real subido a GitHub, rollback real a un commit anterior (verifiqué que un archivo desaparecía), y deploy de vuelta al más reciente (branch `main`, árbol limpio, archivo de regreso).

**Fase 5 — Documentación, Inventario y Notificaciones (completa 2026-07-30)**
Gestión Documental: subida real de archivos por sistema (`multipart/form-data`), almacenados en `E:\PROGRAMACION\Citi-Platform\storage\documents\<slug>\`, descarga vía blob autenticado (un `<a href>` simple no lleva el JWT, hay que pedirlo con axios y crear un object URL). Inventario Tecnológico: CRUD de licencias y dependencias por sistema. Notificaciones: canales cifrados (email/Telegram/Teams/WhatsApp — WhatsApp es solo un stub, falta un proveedor real tipo Twilio/Meta Cloud API), con envío real y verificado: relay SMTP institucional (`172.18.3.57:25`, el mismo que ya usa Sistema de Permisos) probado de extremo a extremo enviando un correo real desde `informatica_lima@pj.gob.pe` ("Informatica CSJ Lima").

**Fase 6 — Infraestructura avanzada**
Servidores de red, VMs, NAS/UPS, multi-sede.

**Fase 7 — IA Institucional**
Asistente con RAG sobre todo el histórico institucional acumulado en fases anteriores.

---

## 8. Por qué este orden

El agente y el control de servicios (Fase 1) van *antes* que backups/config/versiones porque son el requisito de mayor riesgo técnico y seguridad (ejecución remota de comandos) — conviene validar ese modelo pronto y con un solo sistema piloto antes de expandir. La IA institucional va al final porque depende de tener datos históricos reales (logs, auditoría, incidencias) acumulados por la plataforma — construirla antes sería un asistente sin nada que responder.

---

## 9. Próximos pasos concretos (Fase 0)

1. Definir el esquema de base de datos de CITI Core (migraciones Alembic).
2. Levantar el esqueleto FastAPI (auth, RBAC, CRUD de `System`/`Server`/`Service`).
3. Levantar el esqueleto React (shell, login, listado de sistemas).
4. Elegir el sistema piloto para la Fase 1 (recomendado: uno de bajo riesgo, ej. Sistema de Saludos o Sistema de Inventario, no HelpDesk en producción crítica).
