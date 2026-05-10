import enum
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Boolean,
    Float, DateTime, Text, ForeignKey, Enum
)
from sqlalchemy.orm import relationship
from VPSBACKEND.database import Base

# ─────────────────────────────────────────
# Enums
# ─────────────────────────────────────────
class UserRole(str, enum.Enum):
    user  = "user"
    admin = "admin"

class VPSStatus(str, enum.Enum):
    pending   = "pending"
    active    = "active"
    stopped   = "stopped"
    expired   = "expired"
    suspended = "suspended"
    deleted   = "deleted"

class PaymentStatus(str, enum.Enum):
    pending  = "pending"
    verified = "verified"
    rejected = "rejected"

class TicketStatus(str, enum.Enum):
    open   = "open"
    closed = "closed"

class AppealStatus(str, enum.Enum):
    pending  = "pending"
    approved = "approved"
    rejected = "rejected"

class AWSAccountType(str, enum.Enum):
    trial = "trial"
    paid  = "paid"

class BroadcastTarget(str, enum.Enum):
    all   = "all"
    trial = "trial"
    paid  = "paid"

# ─────────────────────────────────────────
# Models
# ─────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id             = Column(Integer, primary_key=True, index=True)
    email          = Column(String(255), unique=True, nullable=False, index=True)
    password_hash  = Column(String(255), nullable=False)
    ip_address     = Column(String(45), nullable=True)
    is_verified    = Column(Boolean, default=False)
    is_suspended   = Column(Boolean, default=False)
    suspend_reason = Column(Text, nullable=True)
    role           = Column(Enum(UserRole), default=UserRole.user)
    wallet_balance = Column(Float, default=0.0)
    created_at     = Column(DateTime, default=datetime.utcnow)
    updated_at     = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    vps_orders    = relationship("VPSOrder", back_populates="user")
    payments      = relationship("Payment", back_populates="user", foreign_keys="Payment.user_id")
    tickets       = relationship("SupportTicket", back_populates="user")
    trial         = relationship("Trial", back_populates="user", uselist=False)
    appeal        = relationship("Appeal", back_populates="user")
    reset_tokens  = relationship("PasswordResetToken", back_populates="user")


class AWSAccount(Base):
    __tablename__ = "aws_accounts"

    id             = Column(Integer, primary_key=True, index=True)
    account_alias  = Column(String(100), nullable=False)
    access_key     = Column(Text, nullable=False)   # AES encrypted
    secret_key     = Column(Text, nullable=False)   # AES encrypted
    region         = Column(String(50), default="ap-south-1")
    type           = Column(Enum(AWSAccountType), nullable=False)
    total_credits  = Column(Float, default=100.0)
    used_credits   = Column(Float, default=0.0)
    is_active      = Column(Boolean, default=True)
    last_synced_at = Column(DateTime, nullable=True)
    created_at     = Column(DateTime, default=datetime.utcnow)

    vps_orders     = relationship("VPSOrder", back_populates="aws_account")

    @property
    def remaining_credits(self):
        return round(self.total_credits - self.used_credits, 4)


class VPSOrder(Base):
    __tablename__ = "vps_orders"

    id                  = Column(Integer, primary_key=True, index=True)
    user_id             = Column(Integer, ForeignKey("users.id"), nullable=False)
    aws_account_id      = Column(Integer, ForeignKey("aws_accounts.id"), nullable=False)

    instance_id         = Column(String(50), unique=True, nullable=True)
    instance_type       = Column(String(50), nullable=False)
    os                  = Column(String(100), nullable=False)
    ami_id              = Column(String(50), nullable=True)
    region              = Column(String(50), nullable=False)

    elastic_ip          = Column(String(45), nullable=True)
    elastic_ip_alloc_id = Column(String(100), nullable=True)
    security_group_id   = Column(String(50), nullable=True)
    key_pair_name       = Column(String(100), nullable=True)
    pem_file_encrypted  = Column(Text, nullable=True)   # AES encrypted

    server_name         = Column(String(100), nullable=True)
    storage_gb          = Column(Integer, default=200)
    extra_storage_gb    = Column(Integer, default=0)
    vcpu                = Column(Integer, nullable=True)
    ram_gb              = Column(Float, nullable=True)

    status              = Column(Enum(VPSStatus), default=VPSStatus.pending)
    expires_at          = Column(DateTime, nullable=True)
    created_at          = Column(DateTime, default=datetime.utcnow)
    updated_at          = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user                = relationship("User", back_populates="vps_orders")
    aws_account         = relationship("AWSAccount", back_populates="vps_orders")
    port_rules          = relationship("PortRule", back_populates="vps")


class Trial(Base):
    __tablename__ = "trials"

    id             = Column(Integer, primary_key=True, index=True)
    user_id        = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    ip_address     = Column(String(45), nullable=False)
    aws_account_id = Column(Integer, ForeignKey("aws_accounts.id"), nullable=True)
    started_at     = Column(DateTime, default=datetime.utcnow)
    expires_at     = Column(DateTime, nullable=False)
    is_used        = Column(Boolean, default=True)

    user           = relationship("User", back_populates="trial")


class Payment(Base):
    __tablename__ = "payments"

    id           = Column(Integer, primary_key=True, index=True)
    user_id      = Column(Integer, ForeignKey("users.id"), nullable=False)
    utr_number   = Column(String(50), unique=True, nullable=False)
    amount       = Column(Float, nullable=False)
    status       = Column(Enum(PaymentStatus), default=PaymentStatus.pending)
    submitted_at = Column(DateTime, default=datetime.utcnow)
    verified_at  = Column(DateTime, nullable=True)
    verified_by  = Column(Integer, ForeignKey("users.id"), nullable=True)
    note         = Column(Text, nullable=True)

    user         = relationship("User", back_populates="payments", foreign_keys=[user_id])


class SupportTicket(Base):
    __tablename__ = "support_tickets"

    id         = Column(Integer, primary_key=True, index=True)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=False)
    subject    = Column(String(255), nullable=False)
    message    = Column(Text, nullable=False)
    status     = Column(Enum(TicketStatus), default=TicketStatus.open)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user       = relationship("User", back_populates="tickets")
    replies    = relationship("TicketReply", back_populates="ticket")


class TicketReply(Base):
    __tablename__ = "ticket_replies"

    id         = Column(Integer, primary_key=True, index=True)
    ticket_id  = Column(Integer, ForeignKey("support_tickets.id"), nullable=False)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=False)
    message    = Column(Text, nullable=False)
    is_admin   = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    ticket     = relationship("SupportTicket", back_populates="replies")


class Appeal(Base):
    __tablename__ = "appeals"

    id          = Column(Integer, primary_key=True, index=True)
    user_id     = Column(Integer, ForeignKey("users.id"), nullable=False)
    reason      = Column(Text, nullable=False)
    status      = Column(Enum(AppealStatus), default=AppealStatus.pending)
    admin_note  = Column(Text, nullable=True)
    created_at  = Column(DateTime, default=datetime.utcnow)
    reviewed_at = Column(DateTime, nullable=True)

    user        = relationship("User", back_populates="appeal")


class Broadcast(Base):
    __tablename__ = "broadcasts"

    id      = Column(Integer, primary_key=True, index=True)
    target  = Column(Enum(BroadcastTarget), nullable=False)
    message = Column(Text, nullable=False)
    sent_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    sent_at = Column(DateTime, default=datetime.utcnow)


class PortRule(Base):
    __tablename__ = "port_rules"

    id         = Column(Integer, primary_key=True, index=True)
    vps_id     = Column(Integer, ForeignKey("vps_orders.id"), nullable=False)
    port       = Column(Integer, nullable=False)
    protocol   = Column(String(10), default="tcp")
    is_open    = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    vps        = relationship("VPSOrder", back_populates="port_rules")


class PlanStock(Base):
    __tablename__ = "plan_stock"

    id            = Column(Integer, primary_key=True, index=True)
    instance_type = Column(String(50), unique=True, nullable=False)
    is_available  = Column(Boolean, default=True)
    updated_at    = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by    = Column(Integer, ForeignKey("users.id"), nullable=True)


# ─────────────────────────────────────────
# Password Reset Token
# ─────────────────────────────────────────

class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id         = Column(Integer, primary_key=True, index=True)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=False)
    token      = Column(String(64), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)
    is_used    = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user       = relationship("User", back_populates="reset_tokens")
    
