import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.docs import DocumentType


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    system_id: uuid.UUID
    title: str
    doc_type: DocumentType
    file_path: str
    version: str | None
    uploaded_by_id: uuid.UUID | None
    uploaded_at: datetime
