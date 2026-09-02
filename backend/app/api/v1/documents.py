import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_permission
from app.core.config import settings
from app.core.database import get_db
from app.models.docs import Document, DocumentType
from app.models.identity import User
from app.models.systems import System
from app.schemas.document import DocumentRead
from app.services.audit import log_action

router = APIRouter(tags=["documents"], dependencies=[Depends(get_current_user)])

STORAGE_ROOT = Path(settings.DOCUMENTS_STORAGE_PATH)


@router.get("/systems/{system_id}/documents", response_model=list[DocumentRead])
def list_documents(system_id: uuid.UUID, db: Session = Depends(get_db)) -> list[Document]:
    query = select(Document).where(Document.system_id == system_id).order_by(Document.uploaded_at.desc())
    return list(db.scalars(query))


@router.post(
    "/systems/{system_id}/documents",
    response_model=DocumentRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("documents.manage"))],
)
async def upload_document(
    system_id: uuid.UUID,
    request: Request,
    title: str = Form(...),
    doc_type: DocumentType = Form(...),
    version: str | None = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Document:
    system = db.get(System, system_id)
    if system is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sistema no encontrado")

    system_dir = STORAGE_ROOT / system.slug
    system_dir.mkdir(parents=True, exist_ok=True)

    safe_name = Path(file.filename or "documento").name
    stored_name = f"{uuid.uuid4()}_{safe_name}"
    dest_path = system_dir / stored_name

    content = await file.read()
    dest_path.write_bytes(content)

    document = Document(
        system_id=system_id,
        title=title,
        doc_type=doc_type,
        file_path=str(dest_path),
        version=version,
        uploaded_by_id=current_user.id,
        uploaded_at=datetime.now(timezone.utc),
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    log_action(
        db, current_user, "document.uploaded", "document", document.id,
        details={"system_id": str(system_id), "title": title, "doc_type": doc_type.value}, request=request,
    )
    return document


@router.get("/documents/{document_id}/download")
def download_document(document_id: uuid.UUID, db: Session = Depends(get_db)) -> FileResponse:
    document = db.get(Document, document_id)
    if document is None or not Path(document.file_path).is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Documento no encontrado")
    filename = Path(document.file_path).name.split("_", 1)[-1]
    return FileResponse(document.file_path, filename=filename)


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_permission("documents.manage"))])
def delete_document(
    document_id: uuid.UUID, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> None:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Documento no encontrado")
    deleted_title = document.title
    Path(document.file_path).unlink(missing_ok=True)
    db.delete(document)
    db.commit()
    log_action(
        db, current_user, "document.deleted", "document", document_id, details={"title": deleted_title}, request=request
    )
