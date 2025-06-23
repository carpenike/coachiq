"""Database schema update models for backup and migration history."""

from datetime import UTC, datetime

from sqlalchemy import JSON, BigInteger, Column, DateTime, Integer, String

from backend.models.database import Base


class DatabaseBackup(Base):
    """Database backup metadata."""

    __tablename__ = "database_backups"

    id = Column(Integer, primary_key=True)
    path = Column(String, nullable=False)
    size_bytes = Column(BigInteger, nullable=False)
    schema_version = Column(String, nullable=False)
    backup_type = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(UTC))


class MigrationHistory(Base):
    """Migration execution history."""

    __tablename__ = "migration_history"

    id = Column(Integer, primary_key=True)
    from_version = Column(String, nullable=False)
    to_version = Column(String, nullable=False)
    status = Column(String, nullable=False)  # success, failed, rolled_back
    duration_ms = Column(Integer, nullable=False)
    details = Column(JSON, nullable=True)
    executed_at = Column(DateTime, nullable=False, default=lambda: datetime.now(UTC))
