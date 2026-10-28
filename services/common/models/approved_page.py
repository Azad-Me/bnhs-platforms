from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base

if TYPE_CHECKING:
    from .page import Page
    from .user import User


class ApprovedPage(Base):
    __tablename__ = "approved_pages"
    __table_args__ = (
        ForeignKeyConstraint(
            ["revision_id", "page_id"],
            ["revisions.id", "revisions.page_id"],
            name="fk_approved_pages_revision",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(start=10000), primary_key=True
    )
    page_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("pages.id"), nullable=False, unique=True
    )
    revision_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    approved_by: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=False, index=True
    )
    approved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    page: Mapped[Page] = relationship(back_populates="approved_page")
    approved_by_user: Mapped[User] = relationship(back_populates="approved_pages")
