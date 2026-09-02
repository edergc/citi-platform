"""RBAC: site-scoped visibility (app/api/deps.py:get_visible_site_ids) and permission
gating (app/api/deps.py:user_has_permission / require_permission)."""

import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import user_has_permission
from app.core.security import create_access_token
from tests.conftest import grant_permission, make_server, make_site, make_user


def _auth_headers(user) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(str(user.id))}"}


def test_site_scoped_technician_only_sees_own_site_servers(client: TestClient, db_session: Session) -> None:
    site_a = make_site(db_session, name="Sede A")
    site_b = make_site(db_session, name="Sede B")
    make_server(db_session, site_id=site_a.id, hostname="server-a")
    make_server(db_session, site_id=site_b.id, hostname="server-b")
    technician = make_user(db_session, dni="55555555")
    technician.sites.append(site_a)
    db_session.commit()

    response = client.get("/api/v1/servers", headers=_auth_headers(technician))

    assert response.status_code == 200
    hostnames = {s["hostname"] for s in response.json()}
    assert hostnames == {"server-a"}


def test_technician_with_no_sites_assigned_sees_nothing(client: TestClient, db_session: Session) -> None:
    site_a = make_site(db_session, name="Sede A")
    make_server(db_session, site_id=site_a.id, hostname="server-a")
    technician = make_user(db_session, dni="66666666")
    db_session.commit()

    response = client.get("/api/v1/servers", headers=_auth_headers(technician))

    assert response.status_code == 200
    assert response.json() == []


def test_superuser_sees_servers_across_all_sites(client: TestClient, db_session: Session) -> None:
    site_a = make_site(db_session, name="Sede A")
    site_b = make_site(db_session, name="Sede B")
    make_server(db_session, site_id=site_a.id, hostname="server-a")
    make_server(db_session, site_id=site_b.id, hostname="server-b")
    admin = make_user(db_session, dni="77777777", is_superuser=True)
    db_session.commit()

    response = client.get("/api/v1/servers", headers=_auth_headers(admin))

    hostnames = {s["hostname"] for s in response.json()}
    assert hostnames == {"server-a", "server-b"}


def test_user_without_permission_is_denied(db_session: Session) -> None:
    user = make_user(db_session, dni="88888888")
    db_session.commit()
    assert user_has_permission(db_session, user, "backups.manage") is False


def test_user_with_granted_permission_is_allowed(db_session: Session) -> None:
    user = make_user(db_session, dni="99999999")
    grant_permission(db_session, user, "backups.manage")
    db_session.commit()
    assert user_has_permission(db_session, user, "backups.manage") is True


def test_superuser_bypasses_permission_checks(db_session: Session) -> None:
    user = make_user(db_session, dni="10101010", is_superuser=True)
    db_session.commit()
    assert user_has_permission(db_session, user, "anything.at.all") is True


def test_permission_gated_endpoint_rejects_without_permission(client: TestClient, db_session: Session) -> None:
    user = make_user(db_session, dni="11011011")
    db_session.commit()

    response = client.post(
        "/api/v1/backup-jobs",
        json={"service_id": str(uuid.uuid4()), "type": "files", "source_path": "x", "storage_path": "y"},
        headers=_auth_headers(user),
    )

    assert response.status_code == 403


def test_permission_gated_endpoint_allows_with_permission(client: TestClient, db_session: Session) -> None:
    """service_id doesn't reference a real Service — confirms the permission gate lets the
    request past to the route body (which then 404s on the fake service, proving we got
    further than the 403 case above, not that the whole operation succeeds)."""
    user = make_user(db_session, dni="12012012")
    grant_permission(db_session, user, "backups.manage")
    db_session.commit()

    response = client.post(
        "/api/v1/backup-jobs",
        json={"service_id": str(uuid.uuid4()), "type": "files", "source_path": "x", "storage_path": "y"},
        headers=_auth_headers(user),
    )

    assert response.status_code == 404
