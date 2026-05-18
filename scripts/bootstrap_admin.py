"""Bootstrap the first org + admin user for a fresh SelfRepair deployment.

Run once after `alembic upgrade head` (or after `docker compose up`
brings the migrate service to completion):

    SELFREPAIR_BOOTSTRAP_ORG=acme \
    SELFREPAIR_BOOTSTRAP_EMAIL=admin@acme.com \
    SELFREPAIR_BOOTSTRAP_PASSWORD='correct-horse-battery-staple' \
    python -m scripts.bootstrap_admin

Idempotent: re-running rotates the password but keeps the same org
and user rows so existing sessions / audit history aren't orphaned.

Never shipped enabled in production by accident: it does nothing
unless the three env vars are set explicitly.
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid

from sqlalchemy import select

from selfrepair.auth.passwords import hash_password
from selfrepair.persistence import get_sessionmaker
from selfrepair.persistence.auth_models import UserCredential
from selfrepair.persistence.models import Org, User, UserRole


def _env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise SystemExit(
            f"missing environment variable: {name}"
        )
    return value


async def _main() -> int:
    org_name = _env("SELFREPAIR_BOOTSTRAP_ORG")
    email = _env("SELFREPAIR_BOOTSTRAP_EMAIL")
    password = _env("SELFREPAIR_BOOTSTRAP_PASSWORD")
    db_url = os.getenv(
        "SELFREPAIR_DATABASE_URL",
        "postgresql+asyncpg://selfrepair:selfrepair@localhost/selfrepair",
    )

    sessionmaker = get_sessionmaker(db_url)
    async with sessionmaker() as session:
        org = (
            await session.execute(
                select(Org).where(Org.name == org_name)
            )
        ).scalar_one_or_none()
        if org is None:
            org = Org(name=org_name)
            session.add(org)
            await session.flush()
            print(f"created org {org.id}")
        else:
            print(f"using existing org {org.id}")

        user = (
            await session.execute(
                select(User)
                .where(User.org_id == org.id, User.email == email)
            )
        ).scalar_one_or_none()
        if user is None:
            user = User(
                org_id=org.id,
                email=email,
                role=UserRole.ADMIN,
            )
            session.add(user)
            await session.flush()
            print(f"created admin user {user.id}")
        else:
            user.role = UserRole.ADMIN
            print(f"upgraded existing user {user.id} to admin")

        cred = await session.get(UserCredential, user.id)
        if cred is None:
            cred = UserCredential(
                user_id=user.id,
                password_hash=hash_password(password),
            )
            session.add(cred)
            print("set initial password")
        else:
            cred.password_hash = hash_password(password)
            print("rotated password")

        await session.commit()

    print(
        f"\nBootstrap complete. Sign in with email={email} "
        "at the SelfRepair console."
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
