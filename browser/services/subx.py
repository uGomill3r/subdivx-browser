import logging
import requests
from dataclasses import dataclass
from django.conf import settings

logger = logging.getLogger(__name__)

SUBX_BASE_URL = "https://subx-api.duckdns.org/api"

# Palabras clave de calidad para fallback
QUALITY_KEYWORDS = {
    "BluRay": ["bluray", "blu-ray", "bdrip", "bluray"],
    "WEBRip": ["webrip", "web-rip"],
    "WEB-DL": ["webdl", "web-dl", "web dl"],
}


@dataclass
class SubtitleResult:
    id: str
    title: str
    description: str
    uploader_name: str
    posted_at: str
    downloads: int
    matched_by: str  # 'user' | 'keyword' | 'quality'


def _get_headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.SUBX_API_KEY}",
        "Content-Type": "application/json",
    }


def search_subtitles(title: str, limit: int = 20) -> list[dict]:
    """
    Busca subtítulos en SubX API por título.
    Retorna lista cruda de resultados.
    """
    url = f"{SUBX_BASE_URL}/subtitles/search"
    params = {"title": title, "limit": limit}

    try:
        response = requests.get(url, headers=_get_headers(), params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        results = data if isinstance(data, list) else data.get("results", [])
        logger.info("Búsqueda '%s' — resultados: %d", title, len(results))
        return results
    except requests.exceptions.HTTPError as e:
        logger.error("HTTP error en búsqueda SubX '%s': %s", title, e)
        return []
    except requests.exceptions.RequestException as e:
        logger.error("Error de red en búsqueda SubX '%s': %s", title, e)
        return []


def filter_by_user(results: list[dict], username: str) -> list[dict]:
    """Filtra resultados por uploader preferido."""
    filtered = [
        r for r in results
        if r.get("uploader_name", "").lower() == username.lower()
    ]
    logger.info("Filtro por usuario '%s' — encontrados: %d", username, len(filtered))
    return filtered


def filter_by_keyword(results: list[dict], keyword: str) -> list[dict]:
    """Filtra resultados cuya descripción contiene la keyword."""
    kw = keyword.lower()
    filtered = [
        r for r in results
        if kw in r.get("description", "").lower()
    ]
    logger.info("Filtro por keyword '%s' — encontrados: %d", keyword, len(filtered))
    return filtered


def filter_by_quality(results: list[dict], release_type: str) -> list[dict]:
    """Filtra resultados por tipo de release (BluRay, WEBRip, WEB-DL)."""
    keywords = QUALITY_KEYWORDS.get(release_type, [release_type.lower()])
    filtered = [
        r for r in results
        if any(kw in r.get("description", "").lower() for kw in keywords)
    ]
    logger.info("Filtro por calidad '%s' — encontrados: %d", release_type, len(filtered))
    return filtered


def search_with_fallback(
    title: str,
    release_type: str,
    keyword: str = "",
) -> tuple[list[SubtitleResult], str]:
    """
    Búsqueda en cascada:
      1. Por usuario preferido (SUBDIVX_PREFERRED_USER)
      2. Por keyword en descripción
      3. Por tipo de release (BluRay / WEBRip / WEB-DL)
      4. Todos los resultados sin filtro

    Retorna (lista_de_resultados, criterio_usado).
    """
    preferred_user = settings.SUBDIVX_PREFERRED_USER
    all_results = search_subtitles(title)

    if not all_results:
        logger.warning("Sin resultados en SubX para: '%s'", title)
        return [], "none"

    # 1. Filtro por usuario preferido
    if preferred_user:
        by_user = filter_by_user(all_results, preferred_user)
        if by_user:
            return _to_subtitle_results(by_user, "user"), "user"

    # 2. Filtro por keyword personalizada
    if keyword:
        by_keyword = filter_by_keyword(all_results, keyword)
        if by_keyword:
            return _to_subtitle_results(by_keyword, "keyword"), "keyword"

    # 3. Filtro por calidad/tipo
    by_quality = filter_by_quality(all_results, release_type)
    if by_quality:
        return _to_subtitle_results(by_quality, "quality"), "quality"

    # 4. Sin filtro — todos los resultados
    logger.info("Sin filtros aplicables, retornando todos los resultados: %d", len(all_results))
    return _to_subtitle_results(all_results, "all"), "all"


def _to_subtitle_results(raw: list[dict], matched_by: str) -> list[SubtitleResult]:
    """Convierte resultados crudos a dataclasses."""
    return [
        SubtitleResult(
            id=str(r.get("id", "")),
            title=r.get("title", ""),
            description=r.get("description", ""),
            uploader_name=r.get("uploader_name", ""),
            posted_at=r.get("posted_at", ""),
            downloads=r.get("downloads", 0),
            matched_by=matched_by,
        )
        for r in raw
    ]


def download_subtitle(subtitle_id: str) -> bytes | None:
    """
    Descarga el archivo .srt de un subtítulo por su ID.
    Retorna los bytes del archivo o None si falla.
    """
    url = f"{SUBX_BASE_URL}/subtitles/{subtitle_id}/download"

    try:
        response = requests.get(url, headers=_get_headers(), timeout=15)
        response.raise_for_status()
        logger.info("Subtítulo descargado — ID: %s — tamaño: %d bytes", subtitle_id, len(response.content))
        return response.content
    except requests.exceptions.HTTPError as e:
        logger.error("HTTP error al descargar subtítulo ID '%s': %s", subtitle_id, e)
        return None
    except requests.exceptions.RequestException as e:
        logger.error("Error de red al descargar subtítulo ID '%s': %s", subtitle_id, e)
        return None
