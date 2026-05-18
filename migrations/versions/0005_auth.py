"""auth: user_credential

Revision ID: 0005_auth
Revises: 0004_console_ops
Create Date: 2026-05-08

Strictly additive. Adds the `user_credential` table backing
password-based auth. The User table itself is intentionally untouched.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_auth"
down_revision: Union[str, Sequence[str], None] = "0004_console_ops"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_credential",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user_account.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("password_hash", sa.String(512), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_password_change_at", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    op.drop_table("user_credential")
