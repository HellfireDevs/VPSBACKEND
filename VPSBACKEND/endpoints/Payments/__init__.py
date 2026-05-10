from datetime import datetime
from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.orm import Session

from VPSBACKEND.database import get_db
from VPSBACKEND.Database.models import Payment, PaymentStatus, User
from VPSBACKEND.Login.Coockis import get_current_user
from VPSBACKEND.utils.limiter import limiter

router = APIRouter(prefix="/api/payment", tags=["Payment"])


# ─────────────────────────────────────────
# POST /api/payment/utr
# ─────────────────────────────────────────

@router.post("/utr")
@limiter.limit("5/hour")
async def submit_utr(
    request:      Request,
    db:           Session = Depends(get_db),
    current_user: dict    = Depends(get_current_user),
):
    body       = await request.json()
    utr_number = body.get("utr_number", "").strip()
    amount     = body.get("amount")

    if not utr_number:
        raise HTTPException(400, "UTR number is required")
    if not amount:
        raise HTTPException(400, "Amount is required")

    try:
        amount = float(amount)
    except (ValueError, TypeError):
        raise HTTPException(400, "Invalid amount")

    if amount <= 0:
        raise HTTPException(400, "Amount must be greater than 0")

    if len(utr_number) < 10 or len(utr_number) > 25:
        raise HTTPException(400, "Invalid UTR number length")

    existing = db.query(Payment).filter(Payment.utr_number == utr_number).first()
    if existing:
        raise HTTPException(409, "This UTR number has already been submitted")

    pending = db.query(Payment).filter(
        Payment.user_id == current_user["user_id"],
        Payment.status  == PaymentStatus.pending,
    ).first()
    if pending:
        raise HTTPException(400, "You already have a pending payment. Please wait for verification")

    payment = Payment(
        user_id    = current_user["user_id"],
        utr_number = utr_number,
        amount     = amount,
        status     = PaymentStatus.pending,
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)

    return {
        "message":      "Payment submitted. Admin will verify within 24 hours",
        "payment_id":   payment.id,
        "utr_number":   payment.utr_number,
        "amount":       payment.amount,
        "status":       payment.status,
        "submitted_at": payment.submitted_at,
    }


# ─────────────────────────────────────────
# GET /api/payment/history
# ─────────────────────────────────────────

@router.get("/history")
async def payment_history(
    request:      Request,
    db:           Session = Depends(get_db),
    current_user: dict    = Depends(get_current_user),
    page:         int     = 1,
    limit:        int     = 20,
):
    if limit > 50:
        limit = 50

    query    = db.query(Payment).filter(Payment.user_id == current_user["user_id"])
    total    = query.count()
    payments = query.order_by(Payment.submitted_at.desc()) \
                    .offset((page - 1) * limit).limit(limit).all()

    return {
        "total": total,
        "page":  page,
        "payments": [
            {
                "id":           p.id,
                "utr_number":   p.utr_number,
                "amount":       p.amount,
                "status":       p.status,
                "submitted_at": p.submitted_at,
                "verified_at":  p.verified_at,
                "note":         p.note,
            }
            for p in payments
        ],
    }


# ─────────────────────────────────────────
# GET /api/wallet/balance
# ─────────────────────────────────────────

wallet_router = APIRouter(prefix="/api/wallet", tags=["Wallet"])

@wallet_router.get("/balance")
async def wallet_balance(
    request:      Request,
    db:           Session = Depends(get_db),
    current_user: dict    = Depends(get_current_user),
):
    user = db.query(User).filter(User.id == current_user["user_id"]).first()
    if not user:
        raise HTTPException(404, "User not found")

    verified_payments = db.query(Payment).filter(
        Payment.user_id == current_user["user_id"],
        Payment.status  == PaymentStatus.verified,
    ).all()

    pending_payments = db.query(Payment).filter(
        Payment.user_id == current_user["user_id"],
        Payment.status  == PaymentStatus.pending,
    ).all()

    return {
        "wallet_balance": round(user.wallet_balance, 2),
        "total_credited": round(sum(p.amount for p in verified_payments), 2),
        "pending_amount": round(sum(p.amount for p in pending_payments), 2),
    }


# ─────────────────────────────────────────
# wallet_router ko main router mein merge
# ─────────────────────────────────────────
router.include_router(wallet_router)
                                    
