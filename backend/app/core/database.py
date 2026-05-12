"""Database configuration and utilities."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.settings import settings

# Database URL
DATABASE_URL = settings.DATABASE_URL

# Create engine with SSL support for Supabase
# Supabase requires SSL connections
engine = create_engine(
    DATABASE_URL,
    echo=settings.ENVIRONMENT == "development",
    pool_pre_ping=True,
    connect_args={"sslmode": "require"} if "supabase" in DATABASE_URL else {},
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()


def get_db():
    """Dependency injection for database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
