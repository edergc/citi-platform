from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class PlatformSecret(Base, UUIDPKMixin, TimestampMixin):
    """CITI-wide secrets not tied to a single service (e.g. the GitHub PAT used for deployments)."""

    __tablename__ = "platform_secrets"

    key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    value_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
