from sqlmodel import Session, SQLModel, create_engine
from sqlalchemy import text
from pathlib import Path
import os

DB_URL = os.getenv("DATABASE_URL", "sqlite:///./data/dude.db")
Path("./data").mkdir(exist_ok=True)

engine = create_engine(DB_URL, echo=False, connect_args={"check_same_thread": False})

# Columns added after initial release — migrate if missing
_MIGRATIONS = [
    "ALTER TABLE device ADD COLUMN mikrotik_user TEXT",
    "ALTER TABLE device ADD COLUMN mikrotik_pass TEXT",
    "ALTER TABLE device ADD COLUMN alias_of INTEGER REFERENCES device(id)",
    "ALTER TABLE device ADD COLUMN edgeswitch_user TEXT",
    "ALTER TABLE device ADD COLUMN edgeswitch_pass TEXT",
    "ALTER TABLE device ADD COLUMN is_deleted INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE device ADD COLUMN tplink_user TEXT",
    "ALTER TABLE device ADD COLUMN tplink_pass TEXT",
    "ALTER TABLE device ADD COLUMN is_manual INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE device ADD COLUMN monitor_id INTEGER",
    "ALTER TABLE device ADD COLUMN alert_status TEXT",
    "ALTER TABLE device ADD COLUMN offline_since DATETIME",
]


def create_db():
    SQLModel.metadata.create_all(engine)
    _run_migrations()


def _run_migrations():
    with engine.connect() as conn:
        for stmt in _MIGRATIONS:
            try:
                conn.execute(text(stmt))
                conn.commit()
            except Exception:
                pass  # column already exists


def get_session():
    with Session(engine) as session:
        yield session
