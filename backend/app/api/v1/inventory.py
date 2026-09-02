import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_permission
from app.core.database import get_db
from app.models.docs import Dependency, License
from app.models.identity import User
from app.schemas.inventory import DependencyCreate, DependencyRead, LicenseCreate, LicenseRead, LicenseUpdate
from app.services.audit import diff_changed_fields, log_action

router = APIRouter(tags=["inventory"], dependencies=[Depends(get_current_user)])


@router.get("/licenses", response_model=list[LicenseRead])
def list_licenses(
    system_id: uuid.UUID | None = None, server_id: uuid.UUID | None = None, db: Session = Depends(get_db)
) -> list[License]:
    query = select(License).order_by(License.expiry_date.asc().nulls_last())
    if system_id is not None:
        query = query.where(License.system_id == system_id)
    if server_id is not None:
        query = query.where(License.server_id == server_id)
    return list(db.scalars(query))


@router.post("/licenses", response_model=LicenseRead, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_permission("inventory.manage"))])
def create_license(
    payload: LicenseCreate, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> License:
    license_ = License(**payload.model_dump())
    db.add(license_)
    db.commit()
    db.refresh(license_)
    log_action(db, current_user, "license.created", "license", license_.id, details={"name": license_.name}, request=request)
    return license_


@router.patch("/licenses/{license_id}", response_model=LicenseRead, dependencies=[Depends(require_permission("inventory.manage"))])
def update_license(
    license_id: uuid.UUID,
    payload: LicenseUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> License:
    license_ = db.get(License, license_id)
    if license_ is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Licencia no encontrada")
    data = payload.model_dump(exclude_unset=True)
    changes = diff_changed_fields(license_, data)
    for field, value in data.items():
        setattr(license_, field, value)
    db.commit()
    db.refresh(license_)
    log_action(
        db, current_user, "license.updated", "license", license_.id,
        details={"changes": changes} if changes else None, request=request,
    )
    return license_


@router.delete("/licenses/{license_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_permission("inventory.manage"))])
def delete_license(
    license_id: uuid.UUID, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> None:
    license_ = db.get(License, license_id)
    if license_ is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Licencia no encontrada")
    deleted_name = license_.name
    db.delete(license_)
    db.commit()
    log_action(
        db, current_user, "license.deleted", "license", license_id, details={"name": deleted_name}, request=request
    )


@router.get("/dependencies", response_model=list[DependencyRead])
def list_dependencies(system_id: uuid.UUID | None = None, db: Session = Depends(get_db)) -> list[Dependency]:
    query = select(Dependency).order_by(Dependency.name)
    if system_id is not None:
        query = query.where(Dependency.system_id == system_id)
    return list(db.scalars(query))


@router.post(
    "/dependencies", response_model=DependencyRead, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_permission("inventory.manage"))]
)
def create_dependency(
    payload: DependencyCreate, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> Dependency:
    dependency = Dependency(**payload.model_dump())
    db.add(dependency)
    db.commit()
    db.refresh(dependency)
    log_action(
        db, current_user, "dependency.created", "dependency", dependency.id,
        details={"name": dependency.name}, request=request,
    )
    return dependency


@router.delete("/dependencies/{dependency_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_permission("inventory.manage"))])
def delete_dependency(
    dependency_id: uuid.UUID, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> None:
    dependency = db.get(Dependency, dependency_id)
    if dependency is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dependencia no encontrada")
    deleted_name = dependency.name
    db.delete(dependency)
    db.commit()
    log_action(
        db, current_user, "dependency.deleted", "dependency", dependency_id,
        details={"name": deleted_name}, request=request,
    )
