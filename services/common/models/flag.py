from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base

if TYPE_CHECKING:
    from .page import Page
    from .user import User


class Flag(Base):
    __tablename__ = "flags"
    __table_args__ = (
        ForeignKeyConstraint(
            ["line_revision_id", "page_id"],
            ["revisions.id", "revisions.page_id"],
            name="fk_flags_line_revision",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(start=10000), primary_key=True
    )
    page_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("pages.id"), nullable=False, index=True
    )
    line_revision_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    created_by: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=False, index=True
    )
    flag_type: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    resolved: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )

    page: Mapped[Page] = relationship(back_populates="flags")
    created_by_user: Mapped[User] = relationship(back_populates="created_flags")
