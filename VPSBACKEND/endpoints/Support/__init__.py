from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.orm import Session

from VPSBACKEND.database import get_db
from VPSBACKEND.Database.models import (
    SupportTicket, TicketReply, TicketStatus
)
from VPSBACKEND.Login.Coockis import get_current_user
from VPSBACKEND.utils.limiter import limiter

router = APIRouter(prefix="/api/support", tags=["Support"])


# ─────────────────────────────────────────
# POST /api/support/ticket
# Naya ticket banao
# ─────────────────────────────────────────

@router.post("/ticket")
@limiter.limit("5/hour")
async def create_ticket(
    request:      Request,
    db:           Session = Depends(get_db),
    current_user: dict    = Depends(get_current_user),
):
    body    = await request.json()
    subject = body.get("subject", "").strip()
    message = body.get("message", "").strip()

    if not subject:
        raise HTTPException(400, "Subject is required")
    if not message:
        raise HTTPException(400, "Message is required")
    if len(subject) > 255:
        raise HTTPException(400, "Subject too long (max 255 characters)")
    if len(message) < 20:
        raise HTTPException(400, "Message too short (min 20 characters)")

    # Open tickets limit — 3 se zyada nahi
    open_count = db.query(SupportTicket).filter(
        SupportTicket.user_id == current_user["user_id"],
        SupportTicket.status  == TicketStatus.open,
    ).count()
    if open_count >= 3:
        raise HTTPException(400, "You already have 3 open tickets. Please wait for resolution")

    ticket = SupportTicket(
        user_id = current_user["user_id"],
        subject = subject,
        message = message,
        status  = TicketStatus.open,
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)

    return {
        "message":    "Ticket created successfully",
        "ticket_id":  ticket.id,
        "subject":    ticket.subject,
        "status":     ticket.status,
        "created_at": ticket.created_at,
    }


# ─────────────────────────────────────────
# GET /api/support/tickets
# User ke saare tickets
# ─────────────────────────────────────────

@router.get("/tickets")
async def list_tickets(
    request:      Request,
    db:           Session = Depends(get_db),
    current_user: dict    = Depends(get_current_user),
    page:         int     = 1,
    limit:        int     = 20,
):
    if limit > 50:
        limit = 50

    query   = db.query(SupportTicket).filter(
        SupportTicket.user_id == current_user["user_id"]
    )
    total   = query.count()
    tickets = query.order_by(SupportTicket.created_at.desc()) \
                   .offset((page - 1) * limit).limit(limit).all()

    return {
        "total": total,
        "page":  page,
        "tickets": [
            {
                "id":           t.id,
                "subject":      t.subject,
                "status":       t.status,
                "reply_count":  len(t.replies),
                "created_at":   t.created_at,
                "updated_at":   t.updated_at,
            }
            for t in tickets
        ],
    }


# ─────────────────────────────────────────
# GET /api/support/ticket/{id}
# Single ticket + replies
# ─────────────────────────────────────────

@router.get("/ticket/{ticket_id}")
async def get_ticket(
    ticket_id:    int,
    request:      Request,
    db:           Session = Depends(get_db),
    current_user: dict    = Depends(get_current_user),
):
    ticket = db.query(SupportTicket).filter(
        SupportTicket.id      == ticket_id,
        SupportTicket.user_id == current_user["user_id"],
    ).first()

    if not ticket:
        raise HTTPException(404, "Ticket not found")

    return {
        "id":         ticket.id,
        "subject":    ticket.subject,
        "message":    ticket.message,
        "status":     ticket.status,
        "created_at": ticket.created_at,
        "updated_at": ticket.updated_at,
        "replies": [
            {
                "id":         r.id,
                "message":    r.message,
                "is_admin":   r.is_admin,
                "created_at": r.created_at,
            }
            for r in sorted(ticket.replies, key=lambda x: x.created_at)
        ],
    }


# ─────────────────────────────────────────
# POST /api/support/ticket/{id}/reply
# User reply kare
# ─────────────────────────────────────────

@router.post("/ticket/{ticket_id}/reply")
@limiter.limit("10/minute")
async def reply_ticket(
    ticket_id:    int,
    request:      Request,
    db:           Session = Depends(get_db),
    current_user: dict    = Depends(get_current_user),
):
    body    = await request.json()
    message = body.get("message", "").strip()

    if not message:
        raise HTTPException(400, "Message is required")
    if len(message) < 5:
        raise HTTPException(400, "Message too short")

    ticket = db.query(SupportTicket).filter(
        SupportTicket.id      == ticket_id,
        SupportTicket.user_id == current_user["user_id"],
    ).first()

    if not ticket:
        raise HTTPException(404, "Ticket not found")

    if ticket.status == TicketStatus.closed:
        raise HTTPException(400, "Cannot reply to a closed ticket")

    reply = TicketReply(
        ticket_id = ticket_id,
        user_id   = current_user["user_id"],
        message   = message,
        is_admin  = False,
    )
    db.add(reply)

    # updated_at refresh karo
    from datetime import datetime
    ticket.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(reply)

    return {
        "message":    "Reply added successfully",
        "reply_id":   reply.id,
        "created_at": reply.created_at,
  }
  
