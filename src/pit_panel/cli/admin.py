"""CLI admin tool for pit-panel."""

import argparse
import asyncio
import sys

from pit_panel.config import Settings
from pit_panel.db.session import get_sessionmaker, init_db
from pit_panel.security.crypto import hash_password


async def create_admin(username: str, password: str, email: str) -> None:
    from sqlalchemy import select

    from pit_panel.db.models import User

    settings = Settings.from_config_file()
    await init_db(settings)

    sessionmaker = get_sessionmaker()
    async with sessionmaker() as db:
        result = await db.execute(select(User).where(User.username == username))
        if result.scalar_one_or_none():
            print(f"User '{username}' already exists.")
            return

        user = User(
            username=username,
            email=email,
            password_hash=hash_password(password, settings),
            is_admin=True,
        )
        db.add(user)
        await db.commit()
        print(f"Admin user '{username}' created.")


async def reset_password(username: str, password: str) -> None:
    from sqlalchemy import select

    from pit_panel.db.models import User

    settings = Settings.from_config_file()
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as db:
        result = await db.execute(select(User).where(User.username == username))
        user = result.scalar_one_or_none()
        if not user:
            print(f"User '{username}' not found.")
            return

        user.password_hash = hash_password(password, settings)
        await db.commit()
        print(f"Password for '{username}' reset.")


def main():  # type: ignore
    parser = argparse.ArgumentParser(description="pit-panel admin CLI")
    sub = parser.add_subparsers(dest="command")

    create = sub.add_parser("create-admin", help="Create admin user")
    create.add_argument("--username", required=True)
    create.add_argument("--password", required=True)
    create.add_argument("--email", required=True)

    reset = sub.add_parser("reset-password", help="Reset user password")
    reset.add_argument("--username", required=True)
    reset.add_argument("--password", required=True)

    args = parser.parse_args()

    if args.command == "create-admin":
        asyncio.run(create_admin(args.username, args.password, args.email))
    elif args.command == "reset-password":
        asyncio.run(reset_password(args.username, args.password))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()  # type: ignore
