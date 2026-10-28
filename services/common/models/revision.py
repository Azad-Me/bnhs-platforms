from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Identity,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base

if TYPE_CHECKING:
    from .page import Page
    from .review import Review
    from .user import User


class Revision(Base):
    __tablename__ = "revisions"
    __table_args__ = (UniqueConstraint("id", "page_id"),)

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(start=10000), primary_key=True
    )
    page_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("pages.id"), nullable=False, index=True
    )
    saved_by: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=False, index=True
    )
    based_on_revision_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("revisions.id"), index=True
    )
    s3_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    saved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    page: Mapped[Page] = relationship(
        back_populates="revisions", foreign_keys=[page_id]
    )
    saved_by_user: Mapped[User] = relationship(
        back_populates="saved_revisions", foreign_keys=[saved_by]
    )
    based_on_revision: Mapped[Revision | None] = relationship(
        remote_side=[id], back_populates="derived_revisions"
    )
    derived_revisions: Mapped[list[Revision]] = relationship(
        back_populates="based_on_revision"
    )
    reviews: Mapped[list[Review]] = relationship(back_populates="revision")
