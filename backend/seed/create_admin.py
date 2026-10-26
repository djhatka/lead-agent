"""
Create YOUR admin login (the platform owner who can see every business).

The demo data already has admin@demo.in / admin1234. On the real website,
delete the demo data and make a proper admin with a strong password:

    .\.venv\Scripts\python.exe -m seed.create_admin you@yourmail.com "Your Name"

It asks for the password without showing it on screen.
"""

import argparse
import getpass

from sqlalchemy import select

from app.database import SessionLocal, init_db
from app.models import User
from app.services.auth_service import create_user


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a platform admin login")
    parser.add_argument("email")
    parser.add_argument("name")
    args = parser.parse_args()

    password = getpass.getpass("Password (min 10 characters): ")
    if len(password) < 10:
        print("Too short. Use at least 10 characters.")
        return
    if getpass.getpass("Type it again: ") != password:
        print("The two passwords don't match.")
        return

    init_db()
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.email == args.email.lower())):
            print("That email already has an account.")
            return
        create_user(db, args.email, args.name, password, role="admin")
    print(f"Admin {args.email} created. Log in with POST /auth/login.")


if __name__ == "__main__":
    main()
