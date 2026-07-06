import logging
import time

import requests
from django.conf import settings

from browser.services.config import get_subx_bridge_url

logger = logging.getLogger(__name__)

# subx-bridge es autohospedado (no tiene una URL pública fija como SubX API),
# por eso la base se resuelve en runtime desde config.json/settings en vez de
# ser una constante como SUBX_BASE_URL.


def _get_base_url() -> str:
    return (get_subx_bridge_url() or "").rstrip("/")


def _get_headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.SUBX_BRIDGE_API_KEY}",
        "Content-Type": "application/json",
    }


def search_subtitles(title: str, year: str = "", limit: int = 20) -> list[dict]:
    """
    Busca subtítulos vía subx-bridge (consulta Subdivx de forma directa).
    Retorna lista cruda de resultados, mismo formato que search_subtitles() de subx.py.
    """
    base_url = _get_base_url()
    if not base_url:
        logger.warning("subx-bridge: URL base no configurada — se omite la búsqueda")
        return []

    url = f"{base_url}/api/subtitles/search"
    # video_type se fija en "movie" porque la app no distingue temporadas/episodios.
    params: dict = {"title": title, "video_type": "movie", "limit": limit}
    if year:
        params["year"] = year

    try:
        response = requests.get(url, headers=_get_headers(), params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        if isinstance(data, list):
            results = data
        else:
            results = data.get("items") or data.get("results", [])
        logger.info("subx-bridge: búsqueda '%s' año=%s — resultados: %d", title, year or "—", len(results))
        return results
    except requests.exceptions.HTTPError as e:
        logger.error("subx-bridge: HTTP error en búsqueda '%s': %s", title, e)
        return []
    except requests.exceptions.RequestException as e:
        logger.error("subx-bridge: error de red en búsqueda '%s': %s", title, e)
        return []


def download_subtitle(subtitle_id: str) -> bytes | None:
    """
    Descarga el archivo comprimido original de Subdivx vía subx-bridge.
    Retorna los bytes del archivo o None si falla.
    """
    base_url = _get_base_url()
    if not base_url:
        logger.warning("subx-bridge: URL base no configurada — no se puede descargar")
        return None

    url = f"{base_url}/api/subtitles/{subtitle_id}/download"

    try:
        response = requests.get(url, headers=_get_headers(), timeout=15)
        response.raise_for_status()
        logger.info("subx-bridge: subtítulo descargado — ID: %s — tamaño: %d bytes", subtitle_id, len(response.content))
        return response.content
    except requests.exceptions.HTTPError as e:
        logger.error("subx-bridge: HTTP error al descargar subtítulo ID '%s': %s", subtitle_id, e)
        return None
    except requests.exceptions.RequestException as e:
        logger.error("subx-bridge: error de red al descargar subtítulo ID '%s': %s", subtitle_id, e)
        return None


def test_api_connection() -> dict:
    """
    Verifica la conexión con subx-bridge:
      1. Que la URL base y la API key estén configuradas.
      2. Que /health responda (no requiere autenticación).
      3. Que una búsqueda de prueba autenticada funcione.

    Retorna un dict con el mismo formato que test_api_connection() de subx.py,
    pensado para mostrarse directo en la UI.
    """
    base_url = _get_base_url()
    if not base_url:
        logger.warning("Test de conexión a subx-bridge: URL base no configurada")
        return {
            "ok": False,
            "status_code": None,
            "message": "Falta configurar la URL de subx-bridge",
            "detail": "Configurá la URL de tu instancia de subx-bridge (ej: http://pibox.lan:8787) "
                      "en la sección de configuración.",
            "elapsed_ms": None,
        }

    if not settings.SUBX_BRIDGE_API_KEY:
        logger.warning("Test de conexión a subx-bridge: SUBX_BRIDGE_API_KEY no está configurada")
        return {
            "ok": False,
            "status_code": None,
            "message": "Falta configurar SUBX_BRIDGE_API_KEY",
            "detail": "La variable de entorno SUBX_BRIDGE_API_KEY está vacía. Sin esto, el bridge "
                      "rechaza cualquier búsqueda (401).",
            "elapsed_ms": None,
        }

    t0 = time.time()
    try:
        health = requests.get(f"{base_url}/health", timeout=10)
        if health.status_code != 200:
            elapsed_ms = int((time.time() - t0) * 1000)
            logger.error("Test de conexión a subx-bridge: /health respondió %d", health.status_code)
            return {
                "ok": False,
                "status_code": health.status_code,
                "message": f"El bridge respondió con un error en /health ({health.status_code})",
                "detail": health.text[:300],
                "elapsed_ms": elapsed_ms,
            }
    except requests.exceptions.Timeout:
        elapsed_ms = int((time.time() - t0) * 1000)
        logger.error("Test de conexión a subx-bridge: timeout en /health tras %d ms", elapsed_ms)
        return {
            "ok": False,
            "status_code": None,
            "message": "Timeout — el bridge no respondió a tiempo",
            "detail": "El servidor no contestó dentro de 10 segundos. Revisá que la URL sea correcta "
                      "y que el servicio esté corriendo.",
            "elapsed_ms": elapsed_ms,
        }
    except requests.exceptions.RequestException as e:
        elapsed_ms = int((time.time() - t0) * 1000)
        logger.error("Test de conexión a subx-bridge: error de red en /health — %s", e)
        return {
            "ok": False,
            "status_code": None,
            "message": "No se pudo conectar con subx-bridge",
            "detail": str(e),
            "elapsed_ms": elapsed_ms,
        }

    url = f"{base_url}/api/subtitles/search"
    params = {"title": "test", "video_type": "movie", "limit": 1}

    try:
        response = requests.get(url, headers=_get_headers(), params=params, timeout=10)
        elapsed_ms = int((time.time() - t0) * 1000)

        if response.status_code == 200:
            logger.info("Test de conexión a subx-bridge: OK (%d ms)", elapsed_ms)
            return {
                "ok": True,
                "status_code": 200,
                "message": "Conexión exitosa",
                "detail": "El bridge respondió correctamente a una búsqueda de prueba.",
                "elapsed_ms": elapsed_ms,
            }

        if response.status_code in (401, 403):
            logger.error(
                "Test de conexión a subx-bridge: auth rechazada (%d) — %s",
                response.status_code, response.text[:300],
            )
            return {
                "ok": False,
                "status_code": response.status_code,
                "message": "API key inválida o rechazada",
                "detail": f"El bridge respondió {response.status_code}. Revisá que SUBX_BRIDGE_API_KEY "
                          f"coincida con alguna de las claves definidas en SUBX_API_KEYS del bridge.",
                "elapsed_ms": elapsed_ms,
            }

        logger.error(
            "Test de conexión a subx-bridge: status inesperado %d — %s",
            response.status_code, response.text[:300],
        )
        return {
            "ok": False,
            "status_code": response.status_code,
            "message": f"El bridge respondió con un error ({response.status_code})",
            "detail": response.text[:300],
            "elapsed_ms": elapsed_ms,
        }

    except requests.exceptions.Timeout:
        elapsed_ms = int((time.time() - t0) * 1000)
        logger.error("Test de conexión a subx-bridge: timeout en búsqueda tras %d ms", elapsed_ms)
        return {
            "ok": False,
            "status_code": None,
            "message": "Timeout — la búsqueda de prueba no respondió a tiempo",
            "detail": "El health check funcionó pero la búsqueda no contestó dentro de 10 segundos.",
            "elapsed_ms": elapsed_ms,
        }
    except requests.exceptions.RequestException as e:
        elapsed_ms = int((time.time() - t0) * 1000)
        logger.error("Test de conexión a subx-bridge: error de red en búsqueda — %s", e)
        return {
            "ok": False,
            "status_code": None,
            "message": "No se pudo completar la búsqueda de prueba",
            "detail": str(e),
            "elapsed_ms": elapsed_ms,
        }
