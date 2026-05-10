import logging
from datetime import datetime
from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from VPSBACKEND.database import get_db
from VPSBACKEND.Database.models import (
    User, UserRole,
    AWSAccount, AWSAccountType,
    VPSOrder, VPSStatus,
    Payment, PaymentStatus,
    SupportTicket, TicketStatus, TicketReply,
    Appeal, AppealStatus,
    Broadcast, BroadcastTarget,
    PlanStock, Trial,
)
from VPSBACKEND.Login.Coockis import require_admin
from VPSBACKEND.utils.limiter import limiter
from VPSBACKEND.utils.encryption import encrypt

logger = logging.getLogger("VPSBACKEND")

router = APIRouter(prefix="/api/admin", tags=["Admin"])


# ══════════════════════════════════════════════
# STATS
# ══════════════════════════════════════════════

@router.get("/stats")
async def get_stats(
    db:    Session = Depends(get_db),
    admin: dict    = Depends(require_admin),
):
    """Dashboard ke liye overall stats."""

    total_users    = db.query(func.count(User.id)).scalar()
    suspended_users= db.query(func.count(User.id)).filter(User.is_suspended == True).scalar()
    total_vps      = db.query(func.count(VPSOrder.id)).filter(VPSOrder.status != VPSStatus.deleted).scalar()
    active_vps     = db.query(func.count(VPSOrder.id)).filter(VPSOrder.status == VPSStatus.active).scalar()
    pending_vps    = db.query(func.count(VPSOrder.id)).filter(VPSOrder.status == VPSStatus.pending).scalar()
    pending_payments = db.query(func.count(Payment.id)).filter(Payment.status == PaymentStatus.pending).scalar()
    open_tickets   = db.query(func.count(SupportTicket.id)).filter(SupportTicket.status == TicketStatus.open).scalar()
    pending_appeals= db.query(func.count(Appeal.id)).filter(Appeal.status == AppealStatus.pending).scalar()
    total_trials   = db.query(func.count(Trial.id)).scalar()

    # AWS accounts credit summary
    aws_accounts = db.query(AWSAccount).filter(AWSAccount.is_active == True).all()
    aws_summary  = [
        {
            "id":                a.id,
            "alias":             a.account_alias,
            "type":              a.type,
            "region":            a.region,
            "total_credits":     a.total_credits,
            "used_credits":      round(a.used_credits, 2),
            "remaining_credits": round(a.remaining_credits, 2),
            "credit_percent":    round((a.used_credits / a.total_credits) * 100, 1) if a.total_credits > 0 else 0,
        }
        for a in aws_accounts
    ]

    return {
        "users": {
            "total":     total_users,
            "suspended": suspended_users,
            "active":    total_users - suspended_users,
        },
        "vps": {
            "total":   total_vps,
            "active":  active_vps,
            "pending": pending_vps,
        },
        "payments": {
            "pending": pending_payments,
        },
        "support": {
            "open_tickets": open_tickets,
        },
        "appeals": {
            "pending": pending_appeals,
        },
        "trials": {
            "total": total_trials,
        },
        "aws_accounts": aws_summary,
    }


# ══════════════════════════════════════════════
# USERS
# ══════════════════════════════════════════════

@router.get("/users")
async def list_users(
    db:     Session = Depends(get_db),
    admin:  dict    = Depends(require_admin),
    page:   int     = 1,
    limit:  int     = 50,
    search: str     = "",
):
    query = db.query(User)

    if search:
        query = query.filter(
            User.email.ilike(f"%{search}%") |
            User.ip_address.ilike(f"%{search}%")
        )

    total = query.count()
    users = query.order_by(User.created_at.desc()) \
                 .offset((page - 1) * limit) \
                 .limit(limit).all()

    return {
        "total": total,
        "page":  page,
        "users": [
            {
                "id":             u.id,
                "email":          u.email,
                "role":           u.role,
                "is_verified":    u.is_verified,
                "is_suspended":   u.is_suspended,
                "suspend_reason": u.suspend_reason,
                "wallet_balance": u.wallet_balance,
                "ip_address":     u.ip_address,
                "created_at":     u.created_at,
                "vps_count":      len([v for v in u.vps_orders if v.status != VPSStatus.deleted]),
            }
            for u in users
        ],
    }


@router.put("/users/{user_id}/suspend")
async def suspend_user(
    user_id: int,
    request: Request,
    db:      Session = Depends(get_db),
    admin:   dict    = Depends(require_admin),
):
    body   = await request.json()
    reason = body.get("reason", "").strip()

    if not reason:
        raise HTTPException(400, "Suspend reason is required")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")

    if user.role == UserRole.admin:
        raise HTTPException(403, "Cannot suspend another admin")

    if user.is_suspended:
        raise HTTPException(400, "User is already suspended")

    user.is_suspended   = True
    user.suspend_reason = reason
    db.commit()

    # Background email
    import asyncio
    asyncio.create_task(_notify_suspension(user.email, reason))

    return {"message": f"User {user.email} suspended successfully"}


@router.put("/users/{user_id}/unsuspend")
async def unsuspend_user(
    user_id: int,
    db:      Session = Depends(get_db),
    admin:   dict    = Depends(require_admin),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")

    if not user.is_suspended:
        raise HTTPException(400, "User is not suspended")

    user.is_suspended   = False
    user.suspend_reason = None
    db.commit()

    import asyncio
    asyncio.create_task(_notify_unsuspension(user.email))

    return {"message": f"User {user.email} unsuspended successfully"}


# ══════════════════════════════════════════════
# AWS ACCOUNTS
# ══════════════════════════════════════════════

@router.get("/aws-accounts")
async def list_aws_accounts(
    db:    Session = Depends(get_db),
    admin: dict    = Depends(require_admin),
):
    accounts = db.query(AWSAccount).order_by(AWSAccount.created_at.desc()).all()

    return {
        "accounts": [
            {
                "id":                a.id,
                "account_alias":     a.account_alias,
                "type":              a.type,
                "region":            a.region,
                "is_active":         a.is_active,
                "total_credits":     a.total_credits,
                "used_credits":      round(a.used_credits, 2),
                "remaining_credits": round(a.remaining_credits, 2),
                "last_synced_at":    a.last_synced_at,
                "created_at":        a.created_at,
                "vps_count":         len(a.vps_orders),
            }
            for a in accounts
        ]
    }


@router.post("/aws-accounts/add")
async def add_aws_account(
    request: Request,
    db:      Session = Depends(get_db),
    admin:   dict    = Depends(require_admin),
):
    body          = await request.json()
    alias         = body.get("account_alias", "").strip()
    access_key    = body.get("access_key", "").strip()
    secret_key    = body.get("secret_key", "").strip()
    region        = body.get("region", "ap-south-1").strip()
    account_type  = body.get("type", "paid")
    total_credits = float(body.get("total_credits", 100.0))

    if not alias or not access_key or not secret_key:
        raise HTTPException(400, "account_alias, access_key, secret_key required")

    if account_type not in ["trial", "paid"]:
        raise HTTPException(400, "type must be 'trial' or 'paid'")

    # Keys encrypt karke store karo
    account = AWSAccount(
        account_alias  = alias,
        access_key     = encrypt(access_key),
        secret_key     = encrypt(secret_key),
        region         = region,
        type           = AWSAccountType(account_type),
        total_credits  = total_credits,
        used_credits   = 0.0,
        is_active      = True,
    )
    db.add(account)
    db.commit()
    db.refresh(account)

    return {
        "message":    "AWS account added successfully",
        "account_id": account.id,
        "alias":      alias,
    }


@router.put("/aws-accounts/{account_id}/toggle")
async def toggle_aws_account(
    account_id: int,
    db:         Session = Depends(get_db),
    admin:      dict    = Depends(require_admin),
):
    account = db.query(AWSAccount).filter(AWSAccount.id == account_id).first()
    if not account:
        raise HTTPException(404, "AWS account not found")

    account.is_active = not account.is_active
    db.commit()

    status = "activated" if account.is_active else "deactivated"
    return {"message": f"AWS account {account.account_alias} {status}", "is_active": account.is_active}


@router.put("/aws-accounts/{account_id}/credits")
async def update_credits(
    account_id: int,
    request:    Request,
    db:         Session = Depends(get_db),
    admin:      dict    = Depends(require_admin),
):
    """Total credits manually update karo."""
    body          = await request.json()
    total_credits = float(body.get("total_credits", 0))

    if total_credits <= 0:
        raise HTTPException(400, "total_credits must be > 0")

    account = db.query(AWSAccount).filter(AWSAccount.id == account_id).first()
    if not account:
        raise HTTPException(404, "AWS account not found")

    account.total_credits = total_credits
    db.commit()

    return {
        "message":           "Credits updated",
        "total_credits":     total_credits,
        "remaining_credits": account.remaining_credits,
    }


# ══════════════════════════════════════════════
# VPS MANAGEMENT (Admin)
# ══════════════════════════════════════════════

@router.get("/vps/all")
async def list_all_vps(
    db:     Session = Depends(get_db),
    admin:  dict    = Depends(require_admin),
    status: str     = "",
    page:   int     = 1,
    limit:  int     = 50,
):
    query = db.query(VPSOrder)

    if status:
        try:
            query = query.filter(VPSOrder.status == VPSStatus(status))
        except ValueError:
            raise HTTPException(400, f"Invalid status. Use: {[s.value for s in VPSStatus]}")

    total   = query.count()
    vps_list= query.order_by(VPSOrder.created_at.desc()) \
                   .offset((page - 1) * limit) \
                   .limit(limit).all()

    return {
        "total": total,
        "page":  page,
        "vps_list": [
            {
                "id":            v.id,
                "user_id":       v.user_id,
                "user_email":    v.user.email if v.user else None,
                "server_name":   v.server_name,
                "instance_id":   v.instance_id,
                "instance_type": v.instance_type,
                "os":            v.os,
                "region":        v.region,
                "elastic_ip":    v.elastic_ip,
                "status":        v.status,
                "storage_gb":    v.storage_gb,
                "aws_account":   v.aws_account.account_alias if v.aws_account else None,
                "expires_at":    v.expires_at,
                "created_at":    v.created_at,
            }
            for v in vps_list
        ],
    }


@router.post("/vps/{vps_id}/force-stop")
async def admin_force_stop_vps(
    vps_id: int,
    db:     Session = Depends(get_db),
    admin:  dict    = Depends(require_admin),
):
    """AWS pe force stop — kisi bhi status se."""
    vps = db.query(VPSOrder).filter(VPSOrder.id == vps_id).first()
    if not vps:
        raise HTTPException(404, "VPS not found")

    if not vps.instance_id:
        raise HTTPException(400, "No EC2 instance linked to this VPS")

    try:
        from VPSBACKEND.utils.aws import get_ec2_from_db_account
        ec2 = get_ec2_from_db_account(vps.aws_account)
        ec2.stop_instances(InstanceIds=[vps.instance_id], Force=True)
        vps.status = VPSStatus.stopped
        db.commit()
        return {"message": f"VPS {vps_id} force stopped", "instance_id": vps.instance_id}
    except Exception as e:
        raise HTTPException(500, f"AWS error: {str(e)}")


@router.post("/vps/{vps_id}/force-start")
async def admin_force_start_vps(
    vps_id: int,
    db:     Session = Depends(get_db),
    admin:  dict    = Depends(require_admin),
):
    vps = db.query(VPSOrder).filter(VPSOrder.id == vps_id).first()
    if not vps:
        raise HTTPException(404, "VPS not found")

    if not vps.instance_id:
        raise HTTPException(400, "No EC2 instance linked to this VPS")

    try:
        from VPSBACKEND.utils.aws import get_ec2_from_db_account
        ec2 = get_ec2_from_db_account(vps.aws_account)
        ec2.start_instances(InstanceIds=[vps.instance_id])
        vps.status = VPSStatus.active
        db.commit()
        return {"message": f"VPS {vps_id} started", "instance_id": vps.instance_id}
    except Exception as e:
        raise HTTPException(500, f"AWS error: {str(e)}")


@router.delete("/vps/{vps_id}/force-delete")
async def admin_force_delete_vps(
    vps_id: int,
    db:     Session = Depends(get_db),
    admin:  dict    = Depends(require_admin),
):
    """AWS resources cleanup + DB delete — kisi bhi status se."""
    vps = db.query(VPSOrder).filter(VPSOrder.id == vps_id).first()
    if not vps:
        raise HTTPException(404, "VPS not found")

    errors = []

    if vps.instance_id and vps.aws_account:
        try:
            from VPSBACKEND.utils.aws import get_ec2_from_db_account
            ec2 = get_ec2_from_db_account(vps.aws_account)

            # Elastic IP release
            if vps.elastic_ip_alloc_id:
                try:
                    ec2.disassociate_address(PublicIp=vps.elastic_ip)
                    ec2.release_address(AllocationId=vps.elastic_ip_alloc_id)
                except Exception as e:
                    errors.append(f"EIP release: {str(e)}")

            # Instance terminate
            try:
                ec2.terminate_instances(InstanceIds=[vps.instance_id])
            except Exception as e:
                errors.append(f"Terminate: {str(e)}")

            # Key pair delete
            if vps.key_pair_name:
                try:
                    ec2.delete_key_pair(KeyName=vps.key_pair_name)
                except Exception as e:
                    errors.append(f"Key pair: {str(e)}")

            # Security group delete (instance terminate ke baad thoda wait)
            if vps.security_group_id:
                import time
                time.sleep(5)
                try:
                    ec2.delete_security_group(GroupId=vps.security_group_id)
                except Exception as e:
                    errors.append(f"SG delete: {str(e)}")

        except Exception as e:
            errors.append(f"AWS client error: {str(e)}")

    vps.status = VPSStatus.deleted
    db.commit()

    return {
        "message": f"VPS {vps_id} deleted",
        "errors":  errors if errors else None,
    }


@router.post("/vps/{vps_id}/fix-stuck")
async def fix_stuck_vps(
    vps_id:  int,
    request: Request,
    db:      Session = Depends(get_db),
    admin:   dict    = Depends(require_admin),
):
    """
    Pending mein stuck VPS ko fix karo.
    Manually status set karo ya AWS se sync karo.
    """
    body       = await request.json()
    new_status = body.get("status")  # active / stopped / expired / deleted

    vps = db.query(VPSOrder).filter(VPSOrder.id == vps_id).first()
    if not vps:
        raise HTTPException(404, "VPS not found")

    # Option 1: AWS se live status sync karo
    if not new_status and vps.instance_id and vps.aws_account:
        try:
            from VPSBACKEND.utils.aws import get_ec2_from_db_account
            ec2      = get_ec2_from_db_account(vps.aws_account)
            response = ec2.describe_instances(InstanceIds=[vps.instance_id])
            inst     = response["Reservations"][0]["Instances"][0]
            state    = inst["State"]["Name"]

            status_map = {
                "running":    VPSStatus.active,
                "stopped":    VPSStatus.stopped,
                "terminated": VPSStatus.deleted,
                "pending":    VPSStatus.pending,
            }
            vps.status = status_map.get(state, VPSStatus.suspended)
            db.commit()

            return {"message": "Status synced from AWS", "aws_state": state, "new_status": vps.status}

        except Exception as e:
            raise HTTPException(500, f"AWS sync failed: {str(e)}")

    # Option 2: Manually set karo
    valid_statuses = [s.value for s in VPSStatus]
    if new_status not in valid_statuses:
        raise HTTPException(400, f"Valid statuses: {valid_statuses}")

    old_status = vps.status
    vps.status = VPSStatus(new_status)
    db.commit()

    logger.info(f"[Admin] VPS {vps_id} status changed: {old_status} → {new_status} by admin {admin['user_id']}")

    return {
        "message":    f"VPS {vps_id} status updated",
        "old_status": old_status,
        "new_status": new_status,
    }


@router.put("/vps/{vps_id}/suspend")
async def admin_suspend_vps(
    vps_id:  int,
    request: Request,
    db:      Session = Depends(get_db),
    admin:   dict    = Depends(require_admin),
):
    body   = await request.json()
    reason = body.get("reason", "Suspended by admin").strip()

    vps = db.query(VPSOrder).filter(VPSOrder.id == vps_id).first()
    if not vps:
        raise HTTPException(404, "VPS not found")

    if vps.status == VPSStatus.suspended:
        raise HTTPException(400, "VPS is already suspended")

    # AWS pe stop karo pehle
    if vps.instance_id and vps.aws_account and vps.status == VPSStatus.active:
        try:
            from VPSBACKEND.utils.aws import get_ec2_from_db_account
            ec2 = get_ec2_from_db_account(vps.aws_account)
            ec2.stop_instances(InstanceIds=[vps.instance_id])
        except Exception as e:
            logger.warning(f"AWS stop failed during suspend: {e}")

    vps.status = VPSStatus.suspended
    db.commit()

    return {"message": f"VPS {vps_id} suspended", "reason": reason}


@router.put("/vps/{vps_id}/unsuspend")
async def admin_unsuspend_vps(
    vps_id: int,
    db:     Session = Depends(get_db),
    admin:  dict    = Depends(require_admin),
):
    vps = db.query(VPSOrder).filter(VPSOrder.id == vps_id).first()
    if not vps:
        raise HTTPException(404, "VPS not found")

    if vps.status != VPSStatus.suspended:
        raise HTTPException(400, "VPS is not suspended")

    vps.status = VPSStatus.stopped  # unsuspend = stopped, user khud start kare
    db.commit()

    return {"message": f"VPS {vps_id} unsuspended (set to stopped)"}


# ══════════════════════════════════════════════
# PAYMENTS
# ══════════════════════════════════════════════

@router.get("/payments/pending")
async def list_pending_payments(
    db:    Session = Depends(get_db),
    admin: dict    = Depends(require_admin),
):
    payments = db.query(Payment) \
                 .filter(Payment.status == PaymentStatus.pending) \
                 .order_by(Payment.submitted_at.asc()) \
                 .all()

    return {
        "count": len(payments),
        "payments": [
            {
                "id":           p.id,
                "user_id":      p.user_id,
                "user_email":   p.user.email if p.user else None,
                "utr_number":   p.utr_number,
                "amount":       p.amount,
                "status":       p.status,
                "submitted_at": p.submitted_at,
            }
            for p in payments
        ],
    }


@router.post("/payments/{payment_id}/verify")
async def verify_payment(
    payment_id: int,
    db:         Session = Depends(get_db),
    admin:      dict    = Depends(require_admin),
):
    payment = db.query(Payment).filter(Payment.id == payment_id).first()
    if not payment:
        raise HTTPException(404, "Payment not found")

    if payment.status != PaymentStatus.pending:
        raise HTTPException(400, f"Payment is already {payment.status.value}")

    # Payment verify + wallet add karo
    payment.status      = PaymentStatus.verified
    payment.verified_at = datetime.utcnow()
    payment.verified_by = admin["user_id"]

    user = db.query(User).filter(User.id == payment.user_id).first()
    if user:
        user.wallet_balance = round(user.wallet_balance + payment.amount, 2)

    db.commit()

    import asyncio
    if user:
        asyncio.create_task(_notify_payment_verified(user.email, payment.amount, user.wallet_balance))

    return {
        "message":     "Payment verified",
        "amount":      payment.amount,
        "new_balance": user.wallet_balance if user else None,
    }


@router.post("/payments/{payment_id}/reject")
async def reject_payment(
    payment_id: int,
    request:    Request,
    db:         Session = Depends(get_db),
    admin:      dict    = Depends(require_admin),
):
    body = await request.json()
    note = body.get("note", "").strip()

    payment = db.query(Payment).filter(Payment.id == payment_id).first()
    if not payment:
        raise HTTPException(404, "Payment not found")

    if payment.status != PaymentStatus.pending:
        raise HTTPException(400, f"Payment is already {payment.status.value}")

    payment.status      = PaymentStatus.rejected
    payment.verified_at = datetime.utcnow()
    payment.verified_by = admin["user_id"]
    payment.note        = note
    db.commit()

    import asyncio
    user = db.query(User).filter(User.id == payment.user_id).first()
    if user:
        asyncio.create_task(_notify_payment_rejected(user.email, payment.amount, note))

    return {"message": "Payment rejected", "note": note}


# ══════════════════════════════════════════════
# SUPPORT TICKETS
# ══════════════════════════════════════════════

@router.get("/support/tickets")
async def list_all_tickets(
    db:     Session = Depends(get_db),
    admin:  dict    = Depends(require_admin),
    status: str     = "open",
    page:   int     = 1,
    limit:  int     = 50,
):
    query = db.query(SupportTicket)

    if status in ["open", "closed"]:
        query = query.filter(SupportTicket.status == TicketStatus(status))

    total   = query.count()
    tickets = query.order_by(SupportTicket.created_at.desc()) \
                   .offset((page - 1) * limit) \
                   .limit(limit).all()

    return {
        "total": total,
        "page":  page,
        "tickets": [
            {
                "id":         t.id,
                "user_id":    t.user_id,
                "user_email": t.user.email if t.user else None,
                "subject":    t.subject,
                "message":    t.message,
                "status":     t.status,
                "reply_count": len(t.replies),
                "created_at": t.created_at,
                "updated_at": t.updated_at,
            }
            for t in tickets
        ],
    }


@router.get("/support/ticket/{ticket_id}")
async def get_ticket_detail(
    ticket_id: int,
    db:        Session = Depends(get_db),
    admin:     dict    = Depends(require_admin),
):
    ticket = db.query(SupportTicket).filter(SupportTicket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(404, "Ticket not found")

    return {
        "id":         ticket.id,
        "user_id":    ticket.user_id,
        "user_email": ticket.user.email if ticket.user else None,
        "subject":    ticket.subject,
        "message":    ticket.message,
        "status":     ticket.status,
        "created_at": ticket.created_at,
        "replies": [
            {
                "id":         r.id,
                "message":    r.message,
                "is_admin":   r.is_admin,
                "user_id":    r.user_id,
                "created_at": r.created_at,
            }
            for r in ticket.replies
        ],
    }


@router.post("/support/ticket/{ticket_id}/reply")
async def admin_reply_ticket(
    ticket_id: int,
    request:   Request,
    db:        Session = Depends(get_db),
    admin:     dict    = Depends(require_admin),
):
    body    = await request.json()
    message = body.get("message", "").strip()

    if not message:
        raise HTTPException(400, "Message is required")

    ticket = db.query(SupportTicket).filter(SupportTicket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(404, "Ticket not found")

    reply = TicketReply(
        ticket_id = ticket_id,
        user_id   = admin["user_id"],
        message   = message,
        is_admin  = True,
    )
    ticket.updated_at = datetime.utcnow()
    db.add(reply)
    db.commit()

    import asyncio
    user = db.query(User).filter(User.id == ticket.user_id).first()
    if user:
        asyncio.create_task(_notify_ticket_reply(user.email, ticket.subject, message))

    return {"message": "Reply sent", "reply_id": reply.id}


@router.put("/support/ticket/{ticket_id}/close")
async def close_ticket(
    ticket_id: int,
    db:        Session = Depends(get_db),
    admin:     dict    = Depends(require_admin),
):
    ticket = db.query(SupportTicket).filter(SupportTicket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(404, "Ticket not found")

    if ticket.status == TicketStatus.closed:
        raise HTTPException(400, "Ticket is already closed")

    ticket.status     = TicketStatus.closed
    ticket.updated_at = datetime.utcnow()
    db.commit()

    return {"message": f"Ticket #{ticket_id} closed"}


# ══════════════════════════════════════════════
# APPEALS
# ══════════════════════════════════════════════

@router.get("/appeals")
async def list_appeals(
    db:    Session = Depends(get_db),
    admin: dict    = Depends(require_admin),
    status: str    = "pending",
):
    query = db.query(Appeal)

    if status in ["pending", "approved", "rejected"]:
        query = query.filter(Appeal.status == AppealStatus(status))

    appeals = query.order_by(Appeal.created_at.asc()).all()

    return {
        "count": len(appeals),
        "appeals": [
            {
                "id":          a.id,
                "user_id":     a.user_id,
                "user_email":  a.user.email if a.user else None,
                "reason":      a.reason,
                "status":      a.status,
                "admin_note":  a.admin_note,
                "created_at":  a.created_at,
                "reviewed_at": a.reviewed_at,
            }
            for a in appeals
        ],
    }


@router.post("/appeal/{appeal_id}/approve")
async def approve_appeal(
    appeal_id: int,
    request:   Request,
    db:        Session = Depends(get_db),
    admin:     dict    = Depends(require_admin),
):
    body = await request.json()
    note = body.get("note", "Your appeal has been approved.").strip()

    appeal = db.query(Appeal).filter(Appeal.id == appeal_id).first()
    if not appeal:
        raise HTTPException(404, "Appeal not found")

    if appeal.status != AppealStatus.pending:
        raise HTTPException(400, f"Appeal is already {appeal.status.value}")

    # Unsuspend user
    user = db.query(User).filter(User.id == appeal.user_id).first()
    if user:
        user.is_suspended   = False
        user.suspend_reason = None

    appeal.status      = AppealStatus.approved
    appeal.admin_note  = note
    appeal.reviewed_at = datetime.utcnow()
    db.commit()

    import asyncio
    if user:
        asyncio.create_task(_notify_appeal_approved(user.email, note))

    return {"message": f"Appeal approved, user {user.email if user else appeal.user_id} unsuspended"}


@router.post("/appeal/{appeal_id}/reject")
async def reject_appeal(
    appeal_id: int,
    request:   Request,
    db:        Session = Depends(get_db),
    admin:     dict    = Depends(require_admin),
):
    body = await request.json()
    note = body.get("note", "").strip()

    if not note:
        raise HTTPException(400, "Rejection note is required")

    appeal = db.query(Appeal).filter(Appeal.id == appeal_id).first()
    if not appeal:
        raise HTTPException(404, "Appeal not found")

    if appeal.status != AppealStatus.pending:
        raise HTTPException(400, f"Appeal is already {appeal.status.value}")

    appeal.status      = AppealStatus.rejected
    appeal.admin_note  = note
    appeal.reviewed_at = datetime.utcnow()
    db.commit()

    import asyncio
    user = db.query(User).filter(User.id == appeal.user_id).first()
    if user:
        asyncio.create_task(_notify_appeal_rejected(user.email, note))

    return {"message": "Appeal rejected"}


# ══════════════════════════════════════════════
# BROADCAST
# ══════════════════════════════════════════════

@router.post("/broadcast")
@limiter.limit("3/hour")
async def send_broadcast(
    request: Request,
    db:      Session = Depends(get_db),
    admin:   dict    = Depends(require_admin),
):
    body    = await request.json()
    message = body.get("message", "").strip()
    target  = body.get("target", "all")

    if not message:
        raise HTTPException(400, "Message is required")

    if target not in ["all", "trial", "paid"]:
        raise HTTPException(400, "target must be 'all', 'trial', or 'paid'")

    # Save broadcast
    broadcast = Broadcast(
        target  = BroadcastTarget(target),
        message = message,
        sent_by = admin["user_id"],
    )
    db.add(broadcast)
    db.commit()

    # Get target users' emails
    query = db.query(User).filter(
        User.is_suspended == False,
        User.is_verified  == True,
    )

    if target == "trial":
        query = query.join(Trial, Trial.user_id == User.id)
    elif target == "paid":
        query = query.join(VPSOrder, VPSOrder.user_id == User.id) \
                     .filter(VPSOrder.status == VPSStatus.active)

    users  = query.distinct().all()
    emails = [u.email for u in users]

    import asyncio
    asyncio.create_task(_send_broadcast_emails(emails, message))

    return {
        "message":      f"Broadcast queued for {len(emails)} users",
        "target":       target,
        "user_count":   len(emails),
        "broadcast_id": broadcast.id,
    }


# ══════════════════════════════════════════════
# PLANS STOCK TOGGLE
# ══════════════════════════════════════════════

@router.put("/plans/{instance_type}/toggle")
async def toggle_plan_stock(
    instance_type: str,
    db:            Session = Depends(get_db),
    admin:         dict    = Depends(require_admin),
):
    """Instance type ko OOS (out of stock) ya available karo."""
    stock = db.query(PlanStock).filter(PlanStock.instance_type == instance_type).first()

    if not stock:
        # Pehli baar → entry create karo
        stock = PlanStock(
            instance_type = instance_type,
            is_available  = False,
            updated_by    = admin["user_id"],
        )
        db.add(stock)
    else:
        stock.is_available = not stock.is_available
        stock.updated_by   = admin["user_id"]
        stock.updated_at   = datetime.utcnow()

    db.commit()

    status = "available" if stock.is_available else "out of stock"
    return {
        "message":       f"{instance_type} is now {status}",
        "instance_type": instance_type,
        "is_available":  stock.is_available,
    }


@router.get("/plans/stock")
async def get_all_stock(
    db:    Session = Depends(get_db),
    admin: dict    = Depends(require_admin),
):
    """Saare OOS instances dekho."""
    stocks = db.query(PlanStock).order_by(PlanStock.instance_type).all()

    return {
        "stock": [
            {
                "instance_type": s.instance_type,
                "is_available":  s.is_available,
                "updated_at":    s.updated_at,
            }
            for s in stocks
        ]
    }


# ══════════════════════════════════════════════
# Background Email Helpers
# ══════════════════════════════════════════════

async def _notify_suspension(email: str, reason: str):
    try:
        from VPSBACKEND.Notification import send_suspension_email
        await send_suspension_email(email, reason)
    except Exception as e:
        logger.error(f"Suspension email failed: {e}")


async def _notify_unsuspension(email: str):
    try:
        from VPSBACKEND.Notification import send_unsuspension_email
        await send_unsuspension_email(email)
    except Exception as e:
        logger.error(f"Unsuspension email failed: {e}")


async def _notify_payment_verified(email: str, amount: float, new_balance: float):
    try:
        from VPSBACKEND.Notification import send_payment_verified_email
        await send_payment_verified_email(email, amount, new_balance)
    except Exception as e:
        logger.error(f"Payment verified email failed: {e}")


async def _notify_payment_rejected(email: str, amount: float, note: str):
    try:
        from VPSBACKEND.Notification import send_payment_rejected_email
        await send_payment_rejected_email(email, amount, note)
    except Exception as e:
        logger.error(f"Payment rejected email failed: {e}")


async def _notify_ticket_reply(email: str, subject: str, message: str):
    try:
        from VPSBACKEND.Notification import send_ticket_reply_email
        await send_ticket_reply_email(email, subject, message)
    except Exception as e:
        logger.error(f"Ticket reply email failed: {e}")


async def _notify_appeal_approved(email: str, note: str):
    try:
        from VPSBACKEND.Notification import send_appeal_approved_email
        await send_appeal_approved_email(email, note)
    except Exception as e:
        logger.error(f"Appeal approved email failed: {e}")


async def _notify_appeal_rejected(email: str, note: str):
    try:
        from VPSBACKEND.Notification import send_appeal_rejected_email
        await send_appeal_rejected_email(email, note)
    except Exception as e:
        logger.error(f"Appeal rejected email failed: {e}")


async def _send_broadcast_emails(emails: list, message: str):
    try:
        from VPSBACKEND.Notification import send_broadcast_email
        for email in emails:
            try:
                await send_broadcast_email(email, message)
            except Exception as e:
                logger.error(f"Broadcast to {email} failed: {e}")
    except Exception as e:
        logger.error(f"Broadcast failed: {e}")
