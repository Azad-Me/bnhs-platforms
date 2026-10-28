from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base

if TYPE_CHECKING:
    from .approved_page import ApprovedPage
    from .assignment import Assignment
    from .flag import Flag
    from .issue import Issue
    from .revision import Revision


class Page(Base):
    __tablename__ = "pages"
    __table_args__ = (
        CheckConstraint("page_number > 0", name="pages_page_number_check"),
        CheckConstraint("width > 0", name="pages_width_check"),
        CheckConstraint("height > 0", name="pages_height_check"),
        CheckConstraint("dpi > 0", name="pages_dpi_check"),
        UniqueConstraint("issue_id", "page_number"),
        ForeignKeyConstraint(
            ["current_approved_revision_id", "id"],
            ["revisions.id", "revisions.page_id"],
            name="fk_pages_current_approved_revision",
            use_alter=True,
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(start=10000), primary_key=True
    )
    issue_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("issues.id"), nullable=False, index=True
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    source_file: Mapped[str] = mapped_column(Text, nullable=False)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    dpi: Mapped[int | None] = mapped_column(Integer)
    master_pdf_s3_key: Mapped[str | None] = mapped_column(Text)
    toned_pdf_s3_key: Mapped[str | None] = mapped_column(Text)
    ocr_s3_key: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    is_check_page: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    current_approved_revision_id: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    issue: Mapped[Issue] = relationship(back_populates="pages")
    assignments: Mapped[list[Assignment]] = relationship(
        back_populates="page", foreign_keys="Assignment.page_id"
    )
    revisions: Mapped[list[Revision]] = relationship(
        back_populates="page", foreign_keys="Revision.page_id"
    )
    approved_page: Mapped[ApprovedPage | None] = relationship(
        back_populates="page", foreign_keys="ApprovedPage.page_id", uselist=False
    )
    flags: Mapped[list[Flag]] = relationship(
        back_populates="page", foreign_keys="Flag.page_id"
    )
