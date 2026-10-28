from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base

if TYPE_CHECKING:
    from .page import Page
    from .volume import Volume


class Issue(Base):
    __tablename__ = "issues"

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(start=1000), primary_key=True
    )
    volume_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("volumes.id"), nullable=False, index=True
    )
    issue_code: Mapped[str] = mapped_column(Text, nullable=False)
    manifest_s3_key: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    volume: Mapped[Volume] = relationship(back_populates="issues")
    pages: Mapped[list[Page]] = relationship(back_populates="issue")
