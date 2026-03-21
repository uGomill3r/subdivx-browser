import logging
import requests
from dataclasses import dataclass
from django.conf import settings
from browser.services.config import get_preferred_user, get_preferred_words, get_release_types, get_resolutions

logger = logging.getLogger(__name__)

SUBX_BASE_URL = "https://subx-api.duckdns.org/api"

# Referencia histórica — los valores activos se leen desde config.json via get_release_types()/get_resolutions()
QUALITY_KEYWORDS = {
    "BluRay": ["bluray", "blu-ray", "bdrip", "brip"],
    "WEBRip": ["webrip", "web-rip"],
    "WEB-DL": ["webdl", "web-dl", "web dl"],
    "HDTV":   ["hdtv"],
}

RESOLUTION_KEYWORDS = {
    "720p":  ["720p", "720"],
    "1080p": ["1080p", "1080", "fhd"],
    "2160p": ["2160p", "2160", "4k", "uhd"],
}


@dataclass
class SubtitleResult:
    id: str
    title: str
    description: str
    uploader_name: str
    posted_at: str
    downloads: int
    matched_by: str  # criterio usado para encontrarlo


def _get_headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.SUBX_API_KEY}",
        "Content-Type": "application/json",
    }


def search_subtitles(title: str, year: str = "", limit: int = 20) -> list[dict]:
    """
    Busca subtítulos en SubX API por título y año opcional.
    Retorna lista cruda de resultados.
    """
    url = f"{SUBX_BASE_URL}/subtitles/search"
    params: dict = {"title": title, "limit": limit}
    if year:
        params["year"] = year

    try:
        response = requests.get(url, headers=_get_headers(), params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        # La API retorna {'items': [...], 'total': N}
        if isinstance(data, list):
            results = data
        else:
            results = data.get("items") or data.get("results", [])
        logger.info("Búsqueda '%s' año=%s — resultados: %d", title, year or "—", len(results))
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
        if (r.get("uploader_name") or "").lower() == username.lower()
    ]
    logger.info("Filtro por usuario '%s' — encontrados: %d", username, len(filtered))
    return filtered


def _keywords_for(name: str, config_list: list[dict], fallback: dict) -> list[str]:
    """
    Busca las keywords configuradas para un nombre dado en la lista de config.
    Si no se encuentra, usa el fallback dict (QUALITY_KEYWORDS o RESOLUTION_KEYWORDS).
    """
    for entry in config_list:
        if entry.get("name", "").lower() == name.lower():
            return entry.get("keywords") or [name.lower()]
    return fallback.get(name, [name.lower()])


def filter_by_quality(results: list[dict], release_type: str) -> list[dict]:
    """Filtra resultados por tipo de release usando keywords desde config.json."""
    keywords = _keywords_for(release_type, get_release_types(), QUALITY_KEYWORDS)
    filtered = [
        r for r in results
        if any(kw in (r.get("description") or "").lower() for kw in keywords)
    ]
    logger.info("Filtro por tipo '%s' keywords=%s — encontrados: %d", release_type, keywords, len(filtered))
    return filtered


def filter_by_resolution(results: list[dict], resolution: str) -> list[dict]:
    """Filtra resultados por resolución usando keywords desde config.json."""
    keywords = _keywords_for(resolution, get_resolutions(), RESOLUTION_KEYWORDS)
    filtered = [
        r for r in results
        if any(kw in (r.get("description") or "").lower() for kw in keywords)
    ]
    logger.info("Filtro por resolución '%s' keywords=%s — encontrados: %d", resolution, keywords, len(filtered))
    return filtered


def filter_by_keyword(results: list[dict], keyword: str) -> list[dict]:
    """
    Filtra resultados cuya descripción contiene todas las palabras de la keyword (AND).
    Las palabras se separan por espacio. Ej: '1080p YIFY' requiere ambas en la descripción.
    """
    words = [w for w in keyword.lower().split() if w]
    if not words:
        return results
    filtered = [
        r for r in results
        if all(w in (r.get("description") or "").lower() for w in words)
    ]
    logger.info("Filtro por keyword %s (AND) — encontrados: %d", words, len(filtered))
    return filtered


def search_by_preferred_user(
    all_results: list[dict],
    preferred_user: str,
    release_type: str,
    resolution: str,
    preferred_words: list[str] | None = None,
) -> tuple[list[SubtitleResult], str] | None:
    """
    Búsqueda en cascada dentro del usuario preferido:
      1. usuario + tipo + resolución + palabras preferidas (si están configuradas)
      2. usuario + tipo + resolución
      3. usuario + tipo
      4. usuario (sin filtros adicionales)

    Retorna (resultados, criterio) o None si no hay resultados del usuario.
    """
    by_user = filter_by_user(all_results, preferred_user)
    if not by_user:
        logger.info("Sin resultados del usuario preferido '%s'", preferred_user)
        return None

    by_type_res = filter_by_resolution(filter_by_quality(by_user, release_type), resolution)

    # 1. usuario + tipo + resolución + palabras preferidas
    if preferred_words and by_type_res:
        filtered = by_type_res
        for word in preferred_words:
            filtered = filter_by_keyword(filtered, word)
        if filtered:
            logger.info("Criterio: usuario + tipo + resolución + palabras %s — resultados: %d", preferred_words, len(filtered))
            return _to_subtitle_results(filtered, "user+type+res+words"), "user+type+res+words"

    # 2. usuario + tipo + resolución
    if by_type_res:
        logger.info("Criterio: usuario + tipo + resolución — resultados: %d", len(by_type_res))
        return _to_subtitle_results(by_type_res, "user+type+res"), "user+type+res"

    # 3. usuario + tipo
    by_type = filter_by_quality(by_user, release_type)
    if by_type:
        logger.info("Criterio: usuario + tipo — resultados: %d", len(by_type))
        return _to_subtitle_results(by_type, "user+type"), "user+type"

    # 4. usuario sin filtros adicionales
    logger.info("Criterio: usuario preferido (sin filtros) — resultados: %d", len(by_user))
    return _to_subtitle_results(by_user, "user"), "user"


def search_with_fallback(
    title: str,
    year: str,
    release_type: str,
    resolution: str,
    keyword: str = "",
) -> tuple[list[SubtitleResult], str]:
    """
    Búsqueda en cascada completa (se usa cuando hay keyword o sin usuario configurado):
      1. keyword en descripción (si se provee)
      2. usuario + tipo + resolución + palabras preferidas
      3. usuario + tipo + resolución
      4. usuario + tipo
      5. usuario (sin filtros)
      6. tipo + resolución (sin usuario)
      7. todos los resultados

    Retorna (lista_de_resultados, criterio_usado).
    """
    preferred_user = get_preferred_user()
    preferred_words = get_preferred_words()
    all_results = search_subtitles(title, year=year)

    if not all_results:
        logger.warning("Sin resultados en SubX para: '%s' (%s)", title, year)
        return [], "none"

    # Si hay keyword explícita del usuario, buscar directo en todos los resultados
    if keyword:
        by_keyword = filter_by_keyword(all_results, keyword)
        if by_keyword:
            logger.info("Búsqueda por keyword '%s' — resultados: %d", keyword, len(by_keyword))
            return _to_subtitle_results(by_keyword, "keyword"), "keyword"

    # Sin keyword: cascada dentro del usuario preferido
    if preferred_user:
        user_result = search_by_preferred_user(all_results, preferred_user, release_type, resolution, preferred_words)
        if user_result:
            return user_result

    # Tipo + resolución sin usuario
    by_type_res = filter_by_resolution(filter_by_quality(all_results, release_type), resolution)
    if by_type_res:
        return _to_subtitle_results(by_type_res, "type+res"), "type+res"

    # Todos los resultados
    logger.info("Sin filtros aplicables, retornando todos: %d", len(all_results))
    return _to_subtitle_results(all_results, "all"), "all"


def get_all_results(title: str, year: str = "") -> list[SubtitleResult]:
    """Retorna todos los resultados de la API sin ningún filtro aplicado."""
    raw = search_subtitles(title, year=year)
    logger.info("get_all_results para '%s' (%s) — total: %d", title, year or "—", len(raw))
    return _to_subtitle_results(raw, "all")


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