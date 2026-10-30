import httpx
import pytest

from app import geoip

IP_API_OK = {"status": "success", "query": "8.8.8.8", "country": "Estados Unidos", "countryCode": "US",
             "regionName": "Virginia", "city": "Ashburn", "isp": "Google LLC", "org": "Google", "as": "AS15169",
             "proxy": False, "hosting": True, "mobile": False, "timezone": "America/New_York", "lat": 39.0, "lon": -77.4}
IPWHO_OK = {"ip": "8.8.8.8", "success": True, "country": "United States", "country_code": "US", "region": "California",
            "city": "Mountain View", "latitude": 37.4, "longitude": -122.0,
            "connection": {"asn": 15169, "org": "Google LLC", "isp": "Google LLC"}, "timezone": {"id": "America/Los_Angeles"}}
IPAPI_CO_OK = {"ip": "8.8.8.8", "city": "Mountain View", "region": "California", "country_name": "United States",
               "country_code": "US", "latitude": 37.4, "longitude": -122.0, "timezone": "America/Los_Angeles",
               "asn": "AS15169", "org": "GOOGLE"}


@pytest.fixture(autouse=True)
def limpio(monkeypatch):
    geoip._cache.clear()
    geoip._pausados.clear()
    yield


def servir(monkeypatch, respuestas):
    """respuestas: {fragmento_de_url: (status, json)}; registra los hosts consultados."""
    visitados = []

    def fake_get(url, **kw):
        visitados.append(url)
        for frag, (st, body) in respuestas.items():
            if frag in url:
                return httpx.Response(st, json=body, request=httpx.Request("GET", url))
        raise AssertionError(f"URL inesperada {url}")

    monkeypatch.setattr(geoip.httpx, "get", fake_get)
    return visitados


def test_usa_ip_api_si_responde(monkeypatch):
    v = servir(monkeypatch, {"ip-api.com": (200, IP_API_OK)})
    r = geoip.localizar_ip("8.8.8.8")
    assert r["proveedor"] == "ip-api" and r["ciudad"] == "Ashburn" and r["es_hosting"] is True
    assert len(v) == 1


def test_429_de_ip_api_pasa_a_ipwho(monkeypatch):
    v = servir(monkeypatch, {"ip-api.com": (429, {}), "ipwho.is": (200, IPWHO_OK)})
    r = geoip.localizar_ip("8.8.8.8")
    assert r["proveedor"] == "ipwho.is" and r["pais"] == "United States" and r["asn"] == "AS15169"
    assert r["es_proxy_o_vpn"] is None  # no se inventa lo que el proveedor no informa


def test_cae_hasta_el_tercero(monkeypatch):
    servir(monkeypatch, {"ip-api.com": (429, {}), "ipwho.is": (429, {}), "ipapi.co": (200, IPAPI_CO_OK)})
    assert geoip.localizar_ip("8.8.8.8")["proveedor"] == "ipapi.co"


def test_pausa_evita_reintentar_el_proveedor_caido(monkeypatch):
    v = servir(monkeypatch, {"ip-api.com": (429, {}), "ipwho.is": (200, IPWHO_OK)})
    geoip.localizar_ip("8.8.8.8")
    geoip.localizar_ip("1.1.1.1")
    assert sum("ip-api.com" in u for u in v) == 1  # la segunda consulta ni lo intento


def test_cache(monkeypatch):
    v = servir(monkeypatch, {"ip-api.com": (200, IP_API_OK)})
    geoip.localizar_ip("8.8.8.8")
    geoip.localizar_ip("8.8.8.8")
    assert len(v) == 1


def test_ip_invalida_no_prueba_otros(monkeypatch):
    v = servir(monkeypatch, {"ip-api.com": (200, {"status": "fail", "message": "invalid query"})})
    with pytest.raises(geoip.GeoIPError, match="invalid query"):
        geoip.localizar_ip("abc")
    assert len(v) == 1


def test_todos_fallan(monkeypatch):
    servir(monkeypatch, {"ip-api.com": (429, {}), "ipwho.is": (500, {}), "ipapi.co": (429, {})})
    with pytest.raises(geoip.GeoIPError, match="ningun proveedor"):
        geoip.localizar_ip("8.8.8.8")
