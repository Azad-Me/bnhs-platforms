from __future__ import annotations

import asyncio

from pydantic import EmailStr, TypeAdapter, ValidationError

from ..common.db import DataBaseConnectionPool
from ..common.env import load_environment
from .service import user_management_service


async def bootstrap_admin() -> None:
    environment = load_environment()
    name = environment.get("BOOTSTRAP_ADMIN_NAME", "").strip()
    email_value = environment.get("BOOTSTRAP_ADMIN_EMAIL", "").strip()
    if not name or not email_value:
        raise RuntimeError(
            "Set BOOTSTRAP_ADMIN_NAME and BOOTSTRAP_ADMIN_EMAIL before bootstrapping."
        )
    if len(name) > 200:
        raise RuntimeError("BOOTSTRAP_ADMIN_NAME must be 200 characters or fewer.")
    try:
        email = str(TypeAdapter(EmailStr).validate_python(email_value)).lower()
    except ValidationError as error:
        raise RuntimeError("BOOTSTRAP_ADMIN_EMAIL must be a valid email address.") from error

    pool = DataBaseConnectionPool()
    try:
        async with pool.session() as session:
            async with session.begin():
                user = await user_management_service.bootstrap_admin(
                    session,
                    name=name,
                    email=email,
                )
    finally:
        await pool.close()
    print(f"Bootstrapped administrator user ID {user.id}.")


def main() -> None:
    asyncio.run(bootstrap_admin())


if __name__ == "__main__":
    main()
