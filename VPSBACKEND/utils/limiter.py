import os
from slowapi import Limiter
from slowapi.util import get_remote_address

# ─────────────────────────────────────────
# Global Rate Limiter
# Sab endpoints isse import karein
# ─────────────────────────────────────────

limiter = Limiter(
    key_func      = get_remote_address,
    default_limits= ["200/minute"],
    storage_uri   = os.getenv("REDIS_URL", "redis://localhost:6379/0"),
)

# ─────────────────────────────────────────
# Endpoint-specific Rate Limits
# ─────────────────────────────────────────

RATE_LIMITS = {
    "auth_login":      "5/minute",
    "auth_register":   "3/minute",
    "auth_forgot":     "3/hour",
    "vps_create":      "5/hour",
    "vps_action":      "20/minute",
    "port_open":       "10/minute",
    "payment_utr":     "5/hour",
    "support_ticket":  "5/hour",
    "appeal_submit":   "2/day",
    "pem_download":    "5/hour",
    "admin_broadcast": "3/hour",
    "global_default":  "200/minute",
}
