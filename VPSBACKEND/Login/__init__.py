from fastapi import APIRouter, Request, HTTPException, Depends, Response
from sqlalchemy.orm import Session
from VPSBACKEND.database import get_db
from VPSBACKEND.Database.models import User
from VPSBACKEND.Login.Coockis import create_token, set_cookie, clear_cookie
from VPSBACKEND.utils.ip_check import check_ip
from VPSBACKEND.utils.turnstile import verify_turnstile
from VPSBACKEND.utils.limiter import limiter            # ← FIX: __main__ nahi, limiter.py se
import bcrypt
import httpx
import asyncio

router = APIRouter(prefix="/api/auth", tags=["Auth"])


# ─────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────

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
    except:
        pass
    return {"city": "Unknown", "region": "Unknown", "country": "Unknown", "isp": "Unknown"}


def get_device_info(request: Request) -> str:
    ua = request.headers.get("user-agent", "Unknown")
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
    return f"{browser} on {os_name} ({device})"


# ─────────────────────────────────────────
# GET /api/auth/me
# ─────────────────────────────────────────

@router.get("/me")
async def get_me(
    request: Request,
    db:      Session = Depends(get_db),
):
    from VPSBACKEND.Login.Coockis import get_current_user
    current_user = get_current_user(request)
    user = db.query(User).filter(User.id == current_user["user_id"]).first()
    if not user:
        raise HTTPException(404, "User not found")

    return {
        "id":           user.id,
        "email":        user.email,
        "role":         user.role,
        "is_verified":  user.is_verified,
        "is_suspended": user.is_suspended,
        "wallet_balance": user.wallet_balance,
        "created_at":   user.created_at,
    }


# ─────────────────────────────────────────
# POST /api/auth/login
# ─────────────────────────────────────────

@router.post("/login")
@limiter.limit("5/minute")
async def login(
    request:      Request,
    response:     Response,
    db:           Session = Depends(get_db),
):
    body     = await request.json()
    email    = body.get("email", "").strip().lower()
    password = body.get("password", "")
    cf_token = body.get("cf_turnstile_token", "")
    ip       = request.client.host

    # ── 1. Basic validation ──
    if not email or not password:
        raise HTTPException(400, "Email and password are required")

    # ── 2. Cloudflare Turnstile CAPTCHA ──
    if not await verify_turnstile(cf_token, ip):
        raise HTTPException(400, "CAPTCHA verification failed")

    # ── 3. VPN / Proxy / Tor check ──
    ip_data = await check_ip(ip)
    if ip_data["is_vpn"]:
        raise HTTPException(403, "VPN is not allowed")
    if ip_data["is_proxy"]:
        raise HTTPException(403, "Proxy is not allowed")
    if ip_data["is_tor"]:
        raise HTTPException(403, "Tor is not allowed")
    if ip_data["fraud_score"] > 75:
        raise HTTPException(403, "Suspicious activity detected")

    # ── 4. Find user ──
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(401, "Invalid email or password")

    # ── 5. Password check ──
    if not bcrypt.checkpw(password.encode(), user.password_hash.encode()):
        raise HTTPException(401, "Invalid email or password")

    # ── 6. Suspended check ──
    if user.is_suspended:
        reason = user.suspend_reason or "No reason provided"
        raise HTTPException(403, f"Account suspended: {reason}")

    # ── 7. Set JWT cookie ──
    token = create_token({"user_id": user.id, "role": user.role})
    set_cookie(response, token)

    # ── 8. Send login alert email (background) ──
    asyncio.create_task(
        _send_login_alert(user.email, ip, request)
    )

    return {
        "message": "Login successful",
        "role":    user.role,
    }


async def _send_login_alert(email: str, ip: str, request: Request):
    from VPSBACKEND.Notification import send_login_email
    location = await get_location(ip)
    device   = get_device_info(request)
    await send_login_email(
        to_email = email,
        ip       = ip,
        device   = device,
        location = location,
    )


# ─────────────────────────────────────────
# POST /api/auth/logout
# ─────────────────────────────────────────

@router.post("/logout")
async def logout(response: Response):
    clear_cookie(response)
    return {"message": "Logged out successfully"}
    
