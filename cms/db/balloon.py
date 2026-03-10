#!/usr/bin/env python3

# Contest Management System - http://cms-dev.github.io/

"""Balloon-related database interface for SQLAlchemy."""

from sqlalchemy.orm import relationship
from sqlalchemy.schema import Column, ForeignKey, UniqueConstraint
from sqlalchemy.types import Boolean, Integer, DateTime, Unicode

from . import Base, Participation, Task, Submission


class Balloon(Base):
    """Tracks a balloon to be given to a contestant for solving a task."""

    __tablename__ = 'balloons'
    __table_args__ = (
        UniqueConstraint('participation_id', 'task_id'),
    )

    id = Column(
        Integer,
        primary_key=True)

    participation_id = Column(
        Integer,
        ForeignKey(Participation.id,
                   onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
        index=True)
    participation = relationship(Participation)

    task_id = Column(
        Integer,
        ForeignKey(Task.id,
                   onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
        index=True)
    task = relationship(Task)

    # The first accepted submission that triggered this balloon.
    submission_id = Column(
        Integer,
        ForeignKey(Submission.id,
                   onupdate="CASCADE", ondelete="SET NULL"),
        nullable=True)
    submission = relationship(Submission)

    # Whether the balloon has been physically delivered.
    delivered = Column(
        Boolean,
        nullable=False,
        default=False)

    delivered_at = Column(
        DateTime,
        nullable=True)
