from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, DateTime, Identity, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base

if TYPE_CHECKING:
    from .approved_page import ApprovedPage
    from .assignment import Assignment
    from .flag import Flag
    from .review import Review
    from .revision import Revision


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(start=1000), primary_key=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    level: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    assignments: Mapped[list[Assignment]] = relationship(
        back_populates="user", foreign_keys="Assignment.user_id"
    )
    saved_revisions: Mapped[list[Revision]] = relationship(
        back_populates="saved_by_user", foreign_keys="Revision.saved_by"
    )
    reviews: Mapped[list[Review]] = relationship(
        back_populates="reviewer", foreign_keys="Review.reviewer_id"
    )
    approved_pages: Mapped[list[ApprovedPage]] = relationship(
        back_populates="approved_by_user", foreign_keys="ApprovedPage.approved_by"
    )
    created_flags: Mapped[list[Flag]] = relationship(
        back_populates="created_by_user", foreign_keys="Flag.created_by"
    )
