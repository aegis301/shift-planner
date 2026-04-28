from app.core.config import settings
from app.db.session import SessionLocal
from app.services.users import ensure_admin_user


def main() -> None:
    with SessionLocal() as db:
        user = ensure_admin_user(db, email=settings.admin_email, password=settings.admin_password)
        print(f"Admin user ready: {user.email}")


if __name__ == "__main__":
    main()

