import httpx
import os

CF_SECRET = os.getenv("CF_TURNSTILE_SECRET")

async def verify_turnstile(token: str, ip: str) -> bool:
    """Verify Cloudflare Turnstile CAPTCHA token"""
    if not CF_SECRET:
        return True  # Dev mode mein skip
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.post(
                "https://challenges.cloudflare.com/turnstile/v0/siteverify",
                data={
                    "secret":   CF_SECRET,
                    "response": token,
                    "remoteip": ip,
                }
            )
        return r.json().get("success", False)
    except:
        return False
