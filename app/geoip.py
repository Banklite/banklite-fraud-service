"""Geolocalizacion real de IPs con ip-api.com (API publica gratuita, sin key).

Limite gratuito: 45 consultas/minuto. Se cachea cada IP 24 h para no agotarlo.
"""

import logging
import time

import httpx

logger = logging.getLogger(__name__)

IP_API_URL = "http://ip-api.com/json/{ip}"
CAMPOS = (
    "status,message,query,country,countryCode,regionName,city,"
    "isp,org,as,proxy,hosting,mobile,timezone,lat,lon"
)
CACHE_TTL = 24 * 3600.0
_cache: dict[str, tuple[float, dict]] = {}


class GeoIPError(Exception):
    pass


def localizar_ip(ip: str) -> dict:
    """Devuelve pais/ciudad/ISP/indicadores de riesgo de la IP."""
    ip = (ip or "").strip()
    if not ip:
        raise GeoIPError("IP vacia")

    ahora = time.time()
    cacheado = _cache.get(ip)
    if cacheado and (ahora - cacheado[0]) < CACHE_TTL:
        return cacheado[1]

    try:
        r = httpx.get(
            IP_API_URL.format(ip=ip),
            params={"fields": CAMPOS, "lang": "es"},
            timeout=6.0,
        )
        r.raise_for_status()
        datos = r.json()
    except Exception as exc:  # noqa: BLE001
        raise GeoIPError(f"No se pudo geolocalizar la IP: {exc}") from exc

    if datos.get("status") != "success":
        raise GeoIPError(datos.get("message") or "IP no valida")

    info = {
        "ip": datos.get("query"),
        "pais": datos.get("country"),
        "codigo_pais": datos.get("countryCode"),
        "region": datos.get("regionName"),
        "ciudad": datos.get("city"),
        "isp": datos.get("isp"),
        "organizacion": datos.get("org"),
        "asn": datos.get("as"),
        "es_proxy_o_vpn": bool(datos.get("proxy")),
        "es_hosting": bool(datos.get("hosting")),
        "es_movil": bool(datos.get("mobile")),
        "zona_horaria": datos.get("timezone"),
        "lat": datos.get("lat"),
        "lon": datos.get("lon"),
    }
    _cache[ip] = (ahora, info)
    logger.info("[IP-API] %s -> %s, %s (%s)", ip, info["pais"], info["ciudad"], info["isp"])
    return info
