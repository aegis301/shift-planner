from app.db.session import SessionLocal
from app.services.work_time_presets import ensure_work_time_presets


def main() -> None:
    with SessionLocal() as db:
        rows = ensure_work_time_presets(db)
        db.commit()
        print(f"Work-time presets ready: {', '.join(row.code for row in rows)}")


if __name__ == "__main__":
    main()
