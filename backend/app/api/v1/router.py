from fastapi import APIRouter

from app.api.v1 import (
    agents,
    alert_rules,
    audit,
    auth,
    backups,
    config,
    deployments,
    documents,
    in_app_notifications,
    inventory,
    maintenance_windows,
    notifications,
    platform_secrets,
    problems,
    public,
    reports,
    roles,
    servers,
    services,
    sites,
    synthetic_checks,
    systems,
    users,
    versions,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(systems.router)
api_router.include_router(servers.router)
api_router.include_router(services.router)
api_router.include_router(agents.router)
api_router.include_router(backups.router)
api_router.include_router(config.router)
api_router.include_router(versions.router)
api_router.include_router(deployments.router)
api_router.include_router(platform_secrets.router)
api_router.include_router(documents.router)
api_router.include_router(inventory.router)
api_router.include_router(notifications.router)
api_router.include_router(public.router)
api_router.include_router(sites.router)
api_router.include_router(roles.router)
api_router.include_router(users.router)
api_router.include_router(audit.router)
api_router.include_router(in_app_notifications.router)
api_router.include_router(alert_rules.router)
api_router.include_router(maintenance_windows.router)
api_router.include_router(problems.router)
api_router.include_router(synthetic_checks.router)
api_router.include_router(reports.router)
