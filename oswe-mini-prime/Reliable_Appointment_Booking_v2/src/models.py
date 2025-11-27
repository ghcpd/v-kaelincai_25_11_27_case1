from sqlalchemy import create_engine, Column, Integer, String, DateTime, Enum, JSON, func, UniqueConstraint
from sqlalchemy.orm import sessionmaker, declarative_base
import enum

Base = declarative_base()

class AppointmentState(str, enum.Enum):
    INIT = 'INIT'
    IN_PROGRESS = 'IN_PROGRESS'
    CONFIRMED = 'CONFIRMED'
    FAILED = 'FAILED'
    CANCELLED = 'CANCELLED'

class Appointment(Base):
    __tablename__ = 'appointments'
    id = Column(Integer, primary_key=True)
    appointment_id = Column(String, unique=True)
    client_id = Column(String)
    slot = Column(String)
    state = Column(Enum(AppointmentState), default=AppointmentState.INIT)
    created_at = Column(DateTime, server_default=func.now())
    meta = Column(JSON, default={})

class IdempotencyKey(Base):
    __tablename__ = 'idempotency_keys'
    id = Column(Integer, primary_key=True)
    key = Column(String, unique=True)
    appointment_id = Column(String)
    response = Column(JSON)
    created_at = Column(DateTime, server_default=func.now())

class Outbox(Base):
    __tablename__ = 'outbox'
    id = Column(Integer, primary_key=True)
    appointment_id = Column(String)
    payload = Column(JSON)
    status = Column(String, default='PENDING')
    attempts = Column(Integer, default=0)
    last_error = Column(String)

def get_engine(echo=False):
    engine = create_engine('sqlite:///appointments.db', connect_args={"check_same_thread": False}, echo=echo)
    return engine

def init_db(echo=False):
    engine = get_engine(echo)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)
