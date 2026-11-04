"""service connectors: encrypted OllaBridge, GitPilot, and MatrixLab rows

Revision ID: 0008_service_connections
Revises: 0007_reviewer
Create Date: 2026-11-04

Additive. Stores Fernet ciphertext in ``secret_enc``. Plaintext tokens are
not written to this table.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_service_connections"
down_revision: Union[str, Sequence[str], None] = "0007_reviewer"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "service_connection",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("org.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("base_url", sa.String(500), nullable=False, server_default=""),
        sa.Column("secret_enc", sa.Text(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="unknown"),
        sa.Column("detail", sa.Text(), nullable=False, server_default=""),
        sa.Column("auth_method", sa.String(32), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_attempted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "org_id",
            "provider",
            name="uq_service_connection_org_provider",
        ),
    )
    op.create_index("ix_service_connection_org_id", "service_connection", ["org_id"])


def downgrade() -> None:
    op.drop_index("ix_service_connection_org_id", table_name="service_connection")
    op.drop_table("service_connection")
