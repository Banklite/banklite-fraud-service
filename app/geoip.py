"""Geolocalizacion real de IPs, con varios proveedores publicos gratuitos y sin key.

Orden: ip-api.com (mas datos: proxy/VPN, hosting, movil) -> ipwho.is -> ipapi.co.
Si un proveedor responde 429 o falla, se pasa al siguiente y se le da una pausa antes de
volver a usarlo (en Render las IPs de salida son compartidas y ip-api gratis permite solo
45 consultas/minuto por IP). Cada IP se cachea 24 h.
"""

import logging
import time

import httpx

logger = logging.getLogger(__name__)

IP_API_URL = "http://ip-api.com/json/{ip}"
IPWHO_URL = "https://ipwho.is/{ip}"
IPAPI_CO_URL = "https://ipapi.co/{ip}/json/"
CAMPOS = (
    "status,message,query,country,countryCode,regionName,city,"
    "isp,org,as,proxy,hosting,mobile,timezone,lat,lon"
)
CACHE_TTL = 24 * 3600.0
PAUSA_PROVEEDOR = 300.0  # segundos sin usar un proveedor que acaba de fallar
TIMEOUT = 6.0

_cache: dict[str, tuple[float, dict]] = {}
_pausados: dict[str, float] = {}


class GeoIPError(Exception):
    pass


def _de_ip_api(ip: str) -> dict:
    r = httpx.get(IP_API_URL.format(ip=ip), params={"fields": CAMPOS, "lang": "es"}, timeout=TIMEOUT)
    r.raise_for_status()
    d = r.json()
    if d.get("status") != "success":
        raise GeoIPError(d.get("message") or "IP no valida")
    return {
        "ip": d.get("query"), "pais": d.get("country"), "codigo_pais": d.get("countryCode"),
        "region": d.get("regionName"), "ciudad": d.get("city"), "isp": d.get("isp"),
        "organizacion": d.get("org"), "asn": d.get("as"),
        "es_proxy_o_vpn": bool(d.get("proxy")), "es_hosting": bool(d.get("hosting")),
        "es_movil": bool(d.get("mobile")), "zona_horaria": d.get("timezone"),
        "lat": d.get("lat"), "lon": d.get("lon"),
    }


def _de_ipwho(ip: str) -> dict:
    r = httpx.get(IPWHO_URL.format(ip=ip), timeout=TIMEOUT)
    r.raise_for_status()
    d = r.json()
    if not d.get("success"):
        raise GeoIPError(d.get("message") or "IP no valida")
    con = d.get("connection") or {}
    tz = d.get("timezone") or {}
    return {
        "ip": d.get("ip"), "pais": d.get("country"), "codigo_pais": d.get("country_code"),
        "region": d.get("region"), "ciudad": d.get("city"), "isp": con.get("isp"),
        "organizacion": con.get("org"), "asn": f"AS{con['asn']}" if con.get("asn") else None,
        "es_proxy_o_vpn": None, "es_hosting": None, "es_movil": None,  # este proveedor no lo informa
        "zona_horaria": tz.get("id"), "lat": d.get("latitude"), "lon": d.get("longitude"),
    }


def _de_ipapi_co(ip: str) -> dict:
    r = httpx.get(IPAPI_CO_URL.format(ip=ip), timeout=TIMEOUT)
    r.raise_for_status()
    d = r.json()
    if d.get("error"):
        raise GeoIPError(d.get("reason") or d.get("message") or "IP no valida")
    return {
        "ip": d.get("ip"), "pais": d.get("country_name"), "codigo_pais": d.get("country_code"),
        "region": d.get("region"), "ciudad": d.get("city"), "isp": d.get("org"),
        "organizacion": d.get("org"), "asn": d.get("asn"),
        "es_proxy_o_vpn": None, "es_hosting": None, "es_movil": None,
        "zona_horaria": d.get("timezone"), "lat": d.get("latitude"), "lon": d.get("longitude"),
    }


PROVEEDORES = [("ip-api", _de_ip_api), ("ipwho.is", _de_ipwho), ("ipapi.co", _de_ipapi_co)]


def localizar_ip(ip: str) -> dict:
    """Devuelve pais/ciudad/ISP/indicadores de riesgo de la IP y el proveedor que respondio."""
    ip = (ip or "").strip()
    if not ip:
        raise GeoIPError("IP vacia")

    ahora = time.time()
    cacheado = _cache.get(ip)
    if cacheado and (ahora - cacheado[0]) < CACHE_TTL:
        return cacheado[1]

    errores = []
    for nombre, fn in PROVEEDORES:
        if _pausados.get(nombre, 0) > ahora:
            errores.append(f"{nombre}: en pausa")
            continue
        try:
            info = fn(ip)
        except GeoIPError as exc:  # la IP es invalida: no tiene sentido probar otro proveedor
            raise exc
        except Exception as exc:  # noqa: BLE001  (429, timeout, red...)
            _pausados[nombre] = ahora + PAUSA_PROVEEDOR
            errores.append(f"{nombre}: {exc}")
            logger.warning("[GeoIP] %s fallo (%s); se prueba otro proveedor", nombre, exc)
            continue
        info["proveedor"] = nombre
        _cache[ip] = (ahora, info)
        logger.info("[GeoIP:%s] %s -> %s, %s (%s)", nombre, ip, info["pais"], info["ciudad"], info["isp"])
        return info

    raise GeoIPError("No se pudo geolocalizar la IP con ningun proveedor: " + " | ".join(errores))
