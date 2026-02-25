from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from .config import get_settings


settings = get_settings()

engine = create_engine(settings.database_url, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

Base = declarative_base()


def init_db() -> None:
    # Import models so that they are registered with Base before create_all
    from . import models  # noqa: F401

    Base.metadata.create_all(bind=engine)

def get_db() -> Session:
    """
    FastAPI dependency that yields a DB session.

    Usage:
      def route(db: Session = Depends(get_db)): ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

