import io
import os
import re
import zipfile
import logging
import tempfile

import requests
from django.conf import settings

from browser.services.subx import SUBX_BASE_URL, filter_by_keyword
from browser.services.subtitle_types import SubtitleResult, to_subtitle_results

try:
    import rarfile
    _RARFILE_AVAILABLE = True
except ImportError:
    _RARFILE_AVAILABLE = False

logger = logging.getLogger(__name__)

# Patrones para detectar el número de temporada en el nombre de una carpeta.
# Se prueban en orden; el primero que matchea gana.
_SEASON_PATTERNS = [
    re.compile(r"(?:season|temporada|temp)\D{0,3}(\d{1,2})\b", re.IGNORECASE),
    re.compile(r"\bs(\d{1,2})\b", re.IGNORECASE),
]


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.SUBX_API_KEY}",
        "Content-Type": "application/json",
    }


def _clean_name(name: str) -> str:
    """Reemplaza separadores típicos de nombres de archivo/carpeta por espacios."""
    cleaned = re.sub(r"[._]+", " ", name)
    return re.sub(r"\s+", " ", cleaned).strip()


def build_search_title(path: str) -> str:
    """
    Arma un título de búsqueda sugerido a partir de la carpeta seleccionada:
    detecta el número de temporada en el nombre de la carpeta y usa el nombre
    de la carpeta padre como nombre de la serie (ej. ".../Breaking Bad/Season 01"
    → "Breaking Bad S01"). Si no encuentra temporada, devuelve el nombre de la
    carpeta tal cual — el usuario siempre puede editar el título antes de buscar.
    """
    clean_path = path.rstrip("/")
    folder_name = os.path.basename(clean_path)
    parent_name = os.path.basename(os.path.dirname(clean_path))

    for pattern in _SEASON_PATTERNS:
        match = pattern.search(folder_name)
        if match:
            season = int(match.group(1))
            series_name = _clean_name(parent_name) or _clean_name(folder_name)
            title = f"{series_name} S{season:02d}"
            logger.debug("Título sugerido desde carpeta '%s': '%s'", folder_name, title)
            return title

    title = _clean_name(folder_name)
    logger.debug("Sin temporada detectada en '%s' — título sugerido: '%s'", folder_name, title)
    return title


def search_subtitles_api(title: str, limit: int = 20) -> list[dict]:
    """
    Busca subtítulos por título contra la API directa de SubDivX.

    A propósito NO respeta el proveedor configurado en Settings (SubX vs
    subx-bridge): para Series siempre se usa la API directa, sin importar
    qué proveedor esté activo para Películas.
    """
    url = f"{SUBX_BASE_URL}/subtitles/search"
    try:
        response = requests.get(url, headers=_headers(), params={"title": title, "limit": limit}, timeout=10)
        response.raise_for_status()
        data = response.json()
        results = data if isinstance(data, list) else (data.get("items") or data.get("results", []))
        logger.info("Búsqueda de series '%s' — resultados: %d", title, len(results))
        return results
    except requests.exceptions.HTTPError as e:
        logger.error("HTTP error en búsqueda de series '%s': %s", title, e)
        return []
    except requests.exceptions.RequestException as e:
        logger.error("Error de red en búsqueda de series '%s': %s", title, e)
        return []


def search(title: str, keyword: str = "", free_query: str = "") -> tuple[list[SubtitleResult], str]:
    """
    Búsqueda de subtítulos para Series:
      - free_query: búsqueda nueva e independiente, ignora `title`.
      - keyword (con title): filtra los resultados de `title` que contengan
        la keyword; si el filtro no deja nada, se devuelven todos los
        resultados de `title` sin filtrar.
      - solo title: resultados de la API tal cual, sin filtros adicionales
        (a diferencia de Películas, acá no se filtra por tipo/resolución).

    Retorna (resultados, criterio_usado).
    """
    if free_query:
        raw = search_subtitles_api(free_query)
        return to_subtitle_results(raw, "free"), "free"

    raw = search_subtitles_api(title)
    if not raw:
        return [], "none"

    if keyword:
        filtered = filter_by_keyword(raw, keyword)
        if filtered:
            return to_subtitle_results(filtered, "keyword"), "keyword"
        logger.info("Keyword '%s' sin resultados — devolviendo todos los de '%s'", keyword, title)

    return to_subtitle_results(raw, "title"), "title"


def download_subtitle(subtitle_id: str) -> bytes | None:
    """
    Descarga un subtítulo (o pack comprimido) por su ID, siempre contra la
    API directa de SubDivX.
    """
    url = f"{SUBX_BASE_URL}/subtitles/{subtitle_id}/download"
    try:
        response = requests.get(url, headers=_headers(), timeout=15)
        response.raise_for_status()
        logger.info("Descarga de series — ID: %s — tamaño: %d bytes", subtitle_id, len(response.content))
        return response.content
    except requests.exceptions.HTTPError as e:
        logger.error("HTTP error al descargar subtítulo de series ID '%s': %s", subtitle_id, e)
        return None
    except requests.exceptions.RequestException as e:
        logger.error("Error de red al descargar subtítulo de series ID '%s': %s", subtitle_id, e)
        return None


def _write_member(data: bytes, name: str, dest_folder: str) -> str:
    dest_path = os.path.join(dest_folder, name)
    if os.path.exists(dest_path):
        logger.warning("Sobrescribiendo subtítulo existente: '%s'", dest_path)
    with open(dest_path, "wb") as f:
        f.write(data)
    return name


def extract_all_subtitles(content: bytes, dest_folder: str) -> list[str]:
    """
    Extrae todos los archivos de subtítulo (según SERIES_SUBTITLE_EXTENSIONS)
    de un pack de temporada (ZIP o RAR) hacia `dest_folder`, sin conservar la
    estructura de subcarpetas interna del comprimido. Si `content` no es un
    comprimido reconocido, se guarda tal cual como un único archivo.

    `dest_folder` debe ser una ruta ya validada (ver renamer.resolve_safe_path).
    Retorna la lista de nombres de archivo guardados.
    """
    extensions = tuple(ext.lower() for ext in settings.SERIES_SUBTITLE_EXTENSIONS)
    saved: list[str] = []

    is_zip = content[:2] == b"PK"
    is_rar = content[:4] == b"Rar!"

    if is_zip:
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                for member in zf.namelist():
                    if not member.lower().endswith(extensions):
                        continue
                    name = os.path.basename(member)
                    if not name:
                        continue
                    saved.append(_write_member(zf.read(member), name, dest_folder))
        except zipfile.BadZipFile as e:
            logger.error("Error al leer ZIP de temporada: %s", e)
            return []

    elif is_rar:
        if not _RARFILE_AVAILABLE:
            logger.error("Archivo RAR recibido pero rarfile no está disponible")
            return []
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".rar", delete=False) as tmp:
                tmp.write(content)
                tmp_path = tmp.name
            with rarfile.RarFile(tmp_path) as rf:
                for member in rf.namelist():
                    if not member.lower().endswith(extensions):
                        continue
                    name = os.path.basename(member)
                    if not name:
                        continue
                    saved.append(_write_member(rf.read(member), name, dest_folder))
        except Exception as e:
            logger.error("Error al leer RAR de temporada: %s", e)
            return []
        finally:
            if tmp_path:
                os.unlink(tmp_path)

    else:
        # No es un comprimido reconocido — se asume un único subtítulo directo.
        saved.append(_write_member(content, "subtitulo_descargado.srt", dest_folder))

    logger.info("Subtítulos extraídos en '%s' — %d archivo(s): %s", dest_folder, len(saved), saved)
    return saved
