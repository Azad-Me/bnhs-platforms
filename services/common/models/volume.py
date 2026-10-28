from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, Identity, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base

if TYPE_CHECKING:
    from .issue import Issue


class Volume(Base):
    __tablename__ = "volumes"

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(start=1000), primary_key=True
    )
    volume_code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    issues: Mapped[list[Issue]] = relationship(back_populates="volume")
