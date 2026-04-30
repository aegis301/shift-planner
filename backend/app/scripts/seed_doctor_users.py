import logging

from sqlalchemy import select

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models import Doctor, User
from app.services.authz import ROLE_DOCTOR
from app.services.users import get_user_by_email

log = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    with SessionLocal() as db:
        doctors = list(
            db.scalars(
                select(Doctor).where(Doctor.user_id.is_(None), Doctor.is_active.is_(True)).order_by(Doctor.id)
            )
        )
        for doctor in doctors:
            email = doctor.email.lower()
            existing = get_user_by_email(db, email)
            if existing is not None:
                log.info("skip doctor id=%s email=%s (user email already exists)", doctor.id, email)
                continue
            user = User(email=email, hashed_password=hash_password(settings.doctor_seed_password), role=ROLE_DOCTOR)
            db.add(user)
            db.flush()
            doctor.user_id = user.id
            db.commit()
            log.info("linked doctor id=%s to new user id=%s", doctor.id, user.id)


if __name__ == "__main__":
    main()
