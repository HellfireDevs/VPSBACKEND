import os
import httpx

from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from VPSBACKEND.database import get_db
from VPSBACKEND.Database.models import User
from VPSBACKEND.Login.Coockis import create_token, set_cookie
from VPSBACKEND.utils.ip_check import check_ip

router = APIRouter(prefix="/api/auth", tags=["OAuth"])

GOOGLE_CLIENT_ID     = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GITHUB_CLIENT_ID     = os.getenv("GITHUB_CLIENT_ID")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET")
FRONTEND_URL         = os.getenv("FRONTEND_URL", "http://localhost:3000")
BACKEND_URL          = os.getenv("BACKEND_URL",  "http://localhost:8000")


# ─────────────────────────────────────────
# Helper: Find or create OAuth user
# ─────────────────────────────────────────

def _find_or_create_user(
    db:       Session,
    email:    str,
    provider: str,
    oauth_id: str,
    ip:       str,
):
    """
    1. Email se user dhundo → existing account link karo
    2. Nahi mila → naya account banao (1 IP = 1 account enforce)
    Returns (user, error_slug)
    """
    user = db.query(User).filter(User.email == email).first()

    if user:
        # Existing user — suspend check
        if user.is_suspended:
            return None, "account_suspended"

        # Provider link karo agar pehle se nahi hai
        if not user.oauth_provider:
            user.oauth_provider = provider
            user.oauth_id       = oauth_id
            db.commit()

        return user, None

    # New user — 1 IP = 1 account
    existing_ip = db.query(User).filter(User.ip_address == ip).first()
    if existing_ip:
        return None, "ip_already_used"

    user = User(
        email          = email,
        password_hash  = None,       # OAuth users ka password nahi hota
        ip_address     = ip,
        is_verified    = True,       # Google/GitHub email already verified hoti hai
        oauth_provider = provider,
        oauth_id       = oauth_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user, None


def _redirect_error(slug: str) -> RedirectResponse:
    return RedirectResponse(f"{FRONTEND_URL}/login?error={slug}")


def _redirect_success(user: User) -> RedirectResponse:
    token    = create_token({"user_id": user.id, "role": user.role})
    response = RedirectResponse(f"{FRONTEND_URL}/dashboard")
    set_cookie(response, token)
    return response


# ══════════════════════════════════════════════
# GOOGLE OAUTH
# ══════════════════════════════════════════════

@router.get("/google")
async def google_login():
    """
    Frontend se redirect karo:
    window.location.href = "/api/auth/google"
    """
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(500, "Google OAuth not configured")

    redirect_uri = f"{BACKEND_URL}/api/auth/google/callback"

    url = (
        "https://accounts.google.com/o/oauth2/v2/auth"
        f"?client_id={GOOGLE_CLIENT_ID}"
        f"&redirect_uri={redirect_uri}"
        f"&response_type=code"
        f"&scope=openid%20email%20profile"
        f"&access_type=offline"
        f"&prompt=select_account"
    )
    return RedirectResponse(url)


@router.get("/google/callback")
async def google_callback(
    request: Request,
    code:    str = None,
    error:   str = None,
    db:      Session = Depends(get_db),
):
    if error or not code:
        return _redirect_error("google_denied")

    ip           = request.client.host
    redirect_uri = f"{BACKEND_URL}/api/auth/google/callback"

    async with httpx.AsyncClient(timeout=10) as client:

        # ── 1. Code → Access Token ──────────────
        token_resp = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code":          code,
                "client_id":     GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri":  redirect_uri,
                "grant_type":    "authorization_code",
            },
        )
        token_data   = token_resp.json()
        access_token = token_data.get("access_token")

        if not access_token:
            return _redirect_error("google_token_failed")

        # ── 2. User info fetch ───────────────────
        info_resp = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        info = info_resp.json()

    email     = info.get("email", "").strip().lower()
    google_id = str(info.get("id", ""))

    if not email:
        return _redirect_error("google_no_email")

    # ── 3. VPN / Proxy check ────────────────────
    ip_data = await check_ip(ip)
    if ip_data["is_vpn"] or ip_data["is_proxy"] or ip_data["is_tor"]:
        return _redirect_error("vpn_not_allowed")

    # ── 4. Find or create user ──────────────────
    user, err = _find_or_create_user(db, email, "google", google_id, ip)
    if err:
        return _redirect_error(err)

    return _redirect_success(user)


# ══════════════════════════════════════════════
# GITHUB OAUTH
# ══════════════════════════════════════════════

@router.get("/github")
async def github_login():
    """
    Frontend se redirect karo:
    window.location.href = "/api/auth/github"
    """
    if not GITHUB_CLIENT_ID:
        raise HTTPException(500, "GitHub OAuth not configured")

    redirect_uri = f"{BACKEND_URL}/api/auth/github/callback"

    url = (
        "https://github.com/login/oauth/authorize"
        f"?client_id={GITHUB_CLIENT_ID}"
        f"&redirect_uri={redirect_uri}"
        f"&scope=user:email"
    )
    return RedirectResponse(url)


@router.get("/github/callback")
async def github_callback(
    request: Request,
    code:    str = None,
    error:   str = None,
    db:      Session = Depends(get_db),
):
    if error or not code:
        return _redirect_error("github_denied")

    ip           = request.client.host
    redirect_uri = f"{BACKEND_URL}/api/auth/github/callback"

    async with httpx.AsyncClient(timeout=10) as client:

        # ── 1. Code → Access Token ──────────────
        token_resp = await client.post(
            "https://github.com/login/oauth/access_token",
            data={
                "code":          code,
                "client_id":     GITHUB_CLIENT_ID,
                "client_secret": GITHUB_CLIENT_SECRET,
                "redirect_uri":  redirect_uri,
            },
            headers={"Accept": "application/json"},
        )
        token_data   = token_resp.json()
        access_token = token_data.get("access_token")

        if not access_token:
            return _redirect_error("github_token_failed")

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept":        "application/json",
        }

        # ── 2. User info ─────────────────────────
        user_resp = await client.get("https://api.github.com/user", headers=headers)
        user_info = user_resp.json()
        github_id = str(user_info.get("id", ""))

        # ── 3. Emails (private emails ke liye) ───
        email_resp = await client.get("https://api.github.com/user/emails", headers=headers)
        emails     = email_resp.json()

    # Primary verified email dhundo
    email = None
    if isinstance(emails, list):
        for e in emails:
            if e.get("primary") and e.get("verified"):
                email = e.get("email", "").strip().lower()
                break

    # Fallback: user info mein public email
    if not email:
        email = (user_info.get("email") or "").strip().lower()

    if not email:
        return _redirect_error("github_no_email")

    # ── 4. VPN / Proxy check ────────────────────
    ip_data = await check_ip(ip)
    if ip_data["is_vpn"] or ip_data["is_proxy"] or ip_data["is_tor"]:
        return _redirect_error("vpn_not_allowed")

    # ── 5. Find or create user ──────────────────
    user, err = _find_or_create_user(db, email, "github", github_id, ip)
    if err:
        return _redirect_error(err)

    return _redirect_success(user)
      
