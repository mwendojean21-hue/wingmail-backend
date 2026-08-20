"""
Geolocalisation approximative par adresse IP, utilisee uniquement pour la
carte admin (pays/region/point approximatif). Ne remplace pas last_lat/lng
qui restent le GPS reel donne volontairement par l'utilisateur pour le jeu.
"""

from typing import Optional
from fastapi import Request
import httpx

# Service gratuit, sans cle API, limite ~45 requetes/minute - largement
# suffisant pour un usage a l'inscription/connexion d'une app naissante.
IP_API_URL = "http://ip-api.com/json/{ip}"
PRIVATE_IP_PREFIXES = ("127.", "10.", "192.168.", "::1", "localhost")


def get_client_ip(request: Request) -> Optional[str]:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


def lookup_ip_geo(ip: str) -> Optional[dict]:
    if not ip or ip.startswith(PRIVATE_IP_PREFIXES):
        return None
    try:
        with httpx.Client(timeout=4.0) as client:
            resp = client.get(
                IP_API_URL.format(ip=ip),
                params={"fields": "status,country,regionName,lat,lon"},
            )
            data = resp.json()
            if data.get("status") == "success":
                return {
                    "country": data.get("country"),
                    "region": data.get("regionName"),
                    "lat": data.get("lat"),
                    "lng": data.get("lon"),
                }
    except (httpx.HTTPError, ValueError):
        pass
    return None
