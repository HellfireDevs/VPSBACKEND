import os
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import QueuePool

# ─────────────────────────────────────────
# Database URL (.env se)
# ─────────────────────────────────────────
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://user:password@localhost:5432/vpsbackend"
)

# ─────────────────────────────────────────
# Engine
# ─────────────────────────────────────────
engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,     # Dead connection auto-check
    pool_recycle=1800,      # 30 min baad connection refresh
    echo=os.getenv("ENV") != "production",  # Dev mein SQL queries log karo
)

# ─────────────────────────────────────────
# Session Factory
# ─────────────────────────────────────────
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

# ─────────────────────────────────────────
# Base Model (Sab models isse inherit karenge)
# ─────────────────────────────────────────
Base = declarative_base()

# ─────────────────────────────────────────
# get_db → Global Dependency
# Har endpoint mein Depends(get_db) se use karo
# ─────────────────────────────────────────
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ─────────────────────────────────────────
# init_db → Startup pe tables create karo
# ─────────────────────────────────────────
def init_db():
    # Saare models import karne chahiye pehle
    from VPSBACKEND.Database.models import (  # noqa: F401
        User, AWSAccount, VPSOrder,
        Trial, Payment, SupportTicket,
        TicketReply, Appeal, Broadcast, PortRule
    )
    Base.metadata.create_all(bind=engine)
    print("✅ Database tables created.")
  
