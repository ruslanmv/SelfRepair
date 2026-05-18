"""ORM tables for password-based auth.

Kept in its own module so the rest of the schema stays free of
security-sensitive columns. `UserCredential` carries the *only* secret
material in Postgres (a PBKDF2 hash); rotating the hashing parameters
is a column-level concern handled here.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from selfrepair.persistence.db import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class UserCredential(Base):
    """Password material for a user.

    `password_hash` format is `pbkdf2_sha256$<iters>$<salt_hex>$<digest_hex>`.
    The plaintext password is never stored; cycling iterations is just
    a write to this row on next login.
    """

    __tablename__ = "user_credential"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user_account.id", ondelete="CASCADE"),
        primary_key=True,
    )
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False,
    )
    last_password_change_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
