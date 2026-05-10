import bcrypt
import asyncio
import os

from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.orm import Session

from VPSBACKEND.database import get_db
from VPSBACKEND.Database.models import User
from VPSBACKEND.utils.ip_check import check_ip
from VPSBACKEND.utils.turnstile import verify_turnstile
from VPSBACKEND.utils.limiter import limiter            # ← FIX: __main__ nahi, limiter.py se
import httpx

router = APIRouter(prefix="/api/auth", tags=["Auth"])

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")


# ─────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────

def is_strong_password(password: str) -> tuple[bool, str]:
    if len(password) < 8:
        return False, "Password must be at least 8 characters"
    if not any(c.isupper() for c in password):
        return False, "Password must contain at least one uppercase letter"
    if not any(c.islower() for c in password):
        return False, "Password must contain at least one lowercase letter"
    if not any(c.isdigit() for c in password):
        return False, "Password must contain at least one number"
    if not any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in password):
        return False, "Password must contain at least one special character"
    return True, ""


def is_valid_email(email: str) -> bool:
    import re
    return bool(re.match(r"^[\w\.-]+@[\w\.-]+\.\w{2,}$", email))


async def get_location(ip: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(
                f"http://ip-api.com/json/{ip}?fields=status,country,regionName,city,isp"
            )
            data = r.json()
            if data.get("status") == "success":
                return {
                    "city":    data.get("city", "Unknown"),
                    "region":  data.get("regionName", "Unknown"),
                    "country": data.get("country", "Unknown"),
                    "isp":     data.get("isp", "Unknown"),
                }
    except Exception:
        pass
    return {"city": "Unknown", "region": "Unknown", "country": "Unknown", "isp": "Unknown"}


# ─────────────────────────────────────────
# POST /api/auth/register
# ─────────────────────────────────────────

@router.post("/register")
@limiter.limit("3/minute")
async def register(
    request: Request,
    db:      Session = Depends(get_db),
):
    body     = await request.json()
    email    = body.get("email", "").strip().lower()
    password = body.get("password", "")
    cf_token = body.get("cf_turnstile_token", "")
    ip       = request.client.host

    # ── 1. Basic validation ──
    if not email or not password:
        raise HTTPException(400, "Email and password are required")

    if not is_valid_email(email):
        raise HTTPException(400, "Invalid email format")

    # ── 2. Password strength ──
    strong, reason = is_strong_password(password)
    if not strong:
        raise HTTPException(400, reason)

    # ── 3. Cloudflare Turnstile CAPTCHA ──
    if not await verify_turnstile(cf_token, ip):
        raise HTTPException(400, "CAPTCHA verification failed")

    # ── 4. VPN / Proxy / Tor check ──
    ip_data = await check_ip(ip)
    if ip_data["is_vpn"]:
        raise HTTPException(403, "VPN is not allowed during registration")
    if ip_data["is_proxy"]:
        raise HTTPException(403, "Proxy is not allowed during registration")
    if ip_data["is_tor"]:
        raise HTTPException(403, "Tor is not allowed during registration")
    if ip_data["fraud_score"] > 75:
        raise HTTPException(403, "Suspicious activity detected")

    # ── 5. 1 IP = 1 account ──
    existing_ip = db.query(User).filter(User.ip_address == ip).first()
    if existing_ip:
        raise HTTPException(403, "An account already exists from this IP address")

    # ── 6. Email already exists ──
    existing_email = db.query(User).filter(User.email == email).first()
    if existing_email:
        raise HTTPException(409, "An account with this email already exists")

    # ── 7. Hash password ──
    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    # ── 8. Create user ──
    user = User(
        email         = email,
        password_hash = password_hash,
        ip_address    = ip,
        is_verified   = False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # ── 9. Send welcome email (background) ──
    asyncio.create_task(
        _send_welcome_alert(email=email, ip=ip, request=request)
    )

    return {
        "message": "Account created successfully. Please verify your email.",
        "user_id": user.id,
    }


async def _send_welcome_alert(email: str, ip: str, request: Request):
    from VPSBACKEND.Notification import send_welcome_email

    location = await get_location(ip)

    ua      = request.headers.get("user-agent", "")
    device  = "Mobile" if "Mobile" in ua else ("Tablet" if "Tablet" in ua else "Desktop")
    browser = next((b for b in ["Edge", "Chrome", "Firefox", "Safari"] if b in ua), "Unknown Browser")
    os_name = (
        "Android" if "Android" in ua else
        "iOS"     if ("iPhone" in ua or "iPad" in ua) else
        "Windows" if "Windows" in ua else
        "MacOS"   if "Mac" in ua else
        "Linux"   if "Linux" in ua else
        "Unknown OS"
    )

    await send_welcome_email(
        to_email    = email,
        ip          = ip,
        device      = f"{browser} on {os_name} ({device})",
        location    = location,
    )
    
