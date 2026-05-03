from sqlmodel import Session, SQLModel, create_engine
from pathlib import Path
import os

DB_URL = os.getenv("DATABASE_URL", "sqlite:///./data/dude.db")
Path("./data").mkdir(exist_ok=True)

engine = create_engine(DB_URL, echo=False, connect_args={"check_same_thread": False})


def create_db():
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session
