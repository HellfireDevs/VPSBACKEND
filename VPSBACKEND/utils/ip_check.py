import httpx
import os

IPQS_KEY = os.getenv("IPQS_API_KEY")

async def check_ip(ip: str) -> dict:
    """Check if IP is VPN, Proxy, or Tor via IPQualityScore"""
    if not IPQS_KEY:
        return {"is_vpn": False, "is_proxy": False, "is_tor": False, "fraud_score": 0}
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(
                f"https://ipqualityscore.com/api/json/ip/{IPQS_KEY}/{ip}"
            )
            data = r.json()
            return {
                "is_vpn":      data.get("vpn", False),
                "is_proxy":    data.get("proxy", False),
                "is_tor":      data.get("tor", False),
                "fraud_score": data.get("fraud_score", 0),
                "country":     data.get("country_code", "??"),
            }
    except:
        return {"is_vpn": False, "is_proxy": False, "is_tor": False, "fraud_score": 0}
