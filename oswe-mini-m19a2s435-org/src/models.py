from sqlalchemy import Column, Integer, String, Text, DateTime, Enum, JSON, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from .db import Base
import enum


class AppointmentStatus(str, enum.Enum):
    INIT = "init"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"


class Appointment(Base):
    __tablename__ = 'appointments'
    id = Column(Integer, primary_key=True, index=True)
    client_request_id = Column(String(255), index=True)
    user_id = Column(String(255), nullable=False)
    slot = Column(String(255), nullable=False)
    status = Column(Enum(AppointmentStatus), default=AppointmentStatus.INIT)
    calendar_event_id = Column(String(255), nullable=True)
    meta = Column(JSON, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())


class IdempotencyRecord(Base):
    __tablename__ = 'idempotency'
    id = Column(Integer, primary_key=True, index=True)
    client_request_id = Column(String(255), unique=True, index=True)
    response_status = Column(String(50))
    response_payload = Column(JSON, nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class Outbox(Base):
    __tablename__ = 'outbox'
    id = Column(Integer, primary_key=True, index=True)
    appointment_id = Column(Integer, ForeignKey('appointments.id'))
    payload = Column(JSON, nullable=False)
    attempts = Column(Integer, default=0)
    max_attempts = Column(Integer, default=2)
    locked = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())
    appointment = relationship('Appointment')
