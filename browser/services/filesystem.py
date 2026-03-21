import os
import re
import zipfile
import logging
from dataclasses import dataclass, field
from django.conf import settings
from browser.services.config import get_media_root

try:
    import rarfile
    _RARFILE_AVAILABLE = True
except ImportError:
    _RARFILE_AVAILABLE = False
    logger_tmp = logging.getLogger(__name__)
    logger_tmp.warning("rarfile no disponible — soporte RAR deshabilitado")

logger = logging.getLogger(__name__)

# Carpeta: solo título y año son requeridos
_TITLE_YEAR_PATTERN = re.compile(
    r'^(?P<title>.+?)\s\((?P<year>\d{4})\)',
    re.IGNORECASE,
)

# Archivo de video: resolución y tipo se leen del nombre del archivo
_RESOLUTION_PATTERN = re.compile(r"\b(?P<resolution>720p|1080p|2160p)\b", re.IGNORECASE)
_TYPE_PATTERN = re.compile(r"\b(?P<type>BluRay|BRRip|BDRip|WEBRip|WEB-DL|HDTV)\b", re.IGNORECASE)

# Normalización de variantes al valor canónico
_TYPE_NORMALIZE = {
    "bluray": "BluRay",
    "brrip":  "BluRay",
    "bdrip":  "BluRay",
    "webrip": "WEBRip",
    "web-dl": "WEB-DL",
    "hdtv":   "HDTV",
}

# Carpetas de subtítulos que se conservan
SUBTITLE_FOLDERS = {"subtitle", "subtitles"}


@dataclass
class FolderInfo:
    folder_name: str
    folder_path: str
    title: str
    year: str
    resolution: str    # extraído del archivo de video principal
    release_type: str  # extraído del archivo de video principal (BluRay / WEBRip / WEB-DL)
    videos: list[str] = field(default_factory=list)
    has_subtitle: bool = False


def parse_folder_name(folder_name: str) -> dict | None:
    """
    Parsea el nombre de carpeta extrayendo solo título y año.
    Retorna None si no se encuentra el formato Título (año).
    """
    match = _TITLE_YEAR_PATTERN.match(folder_name)
    if not match:
        logger.debug("Carpeta sin formato reconocido: '%s'", folder_name)
        return None
    return {
        "title": match.group("title").strip(),
        "year": match.group("year"),
    }


def parse_video_filename(filename: str) -> dict:
    """
    Extrae resolución y tipo de release del nombre del archivo de video.
    Resolución por defecto: '1080p'. Tipo por defecto: 'BluRay'.
    """
    res_match = _RESOLUTION_PATTERN.search(filename)
    type_match = _TYPE_PATTERN.search(filename)

    resolution = res_match.group("resolution").lower() if res_match else "1080p"
    raw_type = type_match.group("type").lower() if type_match else "bluray"
    release_type = _TYPE_NORMALIZE.get(raw_type, "BluRay")

    logger.debug(
        "Archivo '%s' — resolución: %s, tipo: %s",
        filename, resolution, release_type
    )
    return {"resolution": resolution, "release_type": release_type}


def get_videos_in_folder(folder_path: str) -> list[str]:
    """
    Retorna lista de archivos de video (.mp4) dentro de la carpeta.
    """
    try:
        entries = os.listdir(folder_path)
    except OSError as e:
        logger.error("Error al leer carpeta '%s': %s", folder_path, e)
        return []

    videos = [
        f for f in entries
        if os.path.splitext(f)[1].lower() in settings.VIDEO_EXTENSIONS
        and os.path.isfile(os.path.join(folder_path, f))
    ]
    logger.debug("Videos encontrados en '%s': %s", folder_path, videos)
    return sorted(videos)


def check_subtitle_status(folder_path: str, video_filename: str) -> dict:
    """
    Verifica el estado de subtítulos para un video dado.
    Retorna un dict con:
      - has_es_srt: bool — existe video.es.srt
      - has_plain_srt: bool — existe video.srt (sin .es, posiblemente inglés)
      - plain_srt_path: str | None — ruta completa del .srt sin .es
      - es_srt_path: str — ruta esperada del .es.srt
    """
    base = os.path.splitext(video_filename)[0]
    es_srt_path = os.path.join(folder_path, f"{base}.es.srt")
    plain_srt_path = os.path.join(folder_path, f"{base}.srt")

    has_es_srt = os.path.isfile(es_srt_path)
    has_plain_srt = os.path.isfile(plain_srt_path)

    return {
        "has_es_srt": has_es_srt,
        "has_plain_srt": has_plain_srt,
        "plain_srt_path": plain_srt_path if has_plain_srt else None,
        "es_srt_path": es_srt_path,
    }


def subtitle_exists(folder_path: str, video_filename: str) -> bool:
    """
    Verifica si ya existe un subtítulo .es.srt para el video dado.
    """
    status = check_subtitle_status(folder_path, video_filename)
    return status["has_es_srt"]


def rename_plain_srt_to_english(folder_path: str, video_filename: str) -> str | None:
    """
    Si existe video.srt (sin .es), lo renombra a video.en.srt.
    Retorna el nuevo nombre de archivo o None si no había .srt sin .es.
    """
    base = os.path.splitext(video_filename)[0]
    plain_srt_path = os.path.join(folder_path, f"{base}.srt")
    en_srt_path = os.path.join(folder_path, f"{base}.en.srt")

    if not os.path.isfile(plain_srt_path):
        return None

    try:
        os.rename(plain_srt_path, en_srt_path)
        logger.info("Subtítulo renombrado: '%s' → '%s.en.srt'", plain_srt_path, base)
        return f"{base}.en.srt"
    except OSError as e:
        logger.error("Error al renombrar subtítulo '%s': %s", plain_srt_path, e)
        return None


def clean_folder(folder_path: str, video_filename: str) -> list[str]:
    """
    Limpia la carpeta conservando solo:
      - El archivo de video (.mp4)
      - Archivos .srt (cualquier variante)
      - Carpetas llamadas 'subtitle' o 'subtitles'

    Elimina todo lo demás (archivos .nfo, .jpg, .txt, extras, etc.).
    Retorna lista de nombres de archivos eliminados.
    """
    deleted = []

    try:
        entries = os.listdir(folder_path)
    except OSError as e:
        logger.error("Error al leer carpeta para limpieza '%s': %s", folder_path, e)
        return deleted

    for entry in entries:
        full_path = os.path.join(folder_path, entry)

        # Conservar carpetas de subtítulos, ignorar el resto de carpetas
        if os.path.isdir(full_path):
            if entry.lower() in SUBTITLE_FOLDERS:
                logger.debug("Conservando carpeta de subtítulos: '%s'", entry)
            else:
                logger.debug("Ignorando carpeta desconocida: '%s'", entry)
            continue

        # Conservar el video principal
        if entry == video_filename:
            continue

        # Conservar cualquier .srt
        if entry.lower().endswith(".srt"):
            continue

        # Eliminar el resto
        try:
            os.remove(full_path)
            deleted.append(entry)
            logger.debug("Archivo eliminado: '%s'", entry)
        except OSError as e:
            logger.error("Error al eliminar '%s': %s", full_path, e)

    if deleted:
        logger.info("Limpieza de '%s' — eliminados %d archivos: %s", folder_path, len(deleted), deleted)
    else:
        logger.info("Limpieza de '%s' — sin archivos para eliminar", folder_path)

    return deleted


def list_media_folders() -> list[FolderInfo]:
    """
    Lista todas las carpetas en MEDIA_ROOT_PATH con formato válido.
    Retorna lista de FolderInfo ordenada por título.
    """
    media_root = get_media_root()

    try:
        entries = os.listdir(media_root)
    except OSError as e:
        logger.error("Error al leer MEDIA_ROOT '%s': %s", media_root, e)
        return []

    excluded = settings.MEDIA_EXCLUDED_FOLDERS
    folders = []
    for entry in sorted(entries):
        # Saltar carpetas excluidas antes de cualquier acceso al disco
        if entry in excluded:
            logger.debug("Carpeta excluida del escaneo: '%s'", entry)
            continue

        full_path = os.path.join(media_root, entry)
        if not os.path.isdir(full_path):
            continue

        parsed = parse_folder_name(entry)
        if not parsed:
            continue

        videos = get_videos_in_folder(full_path)

        # Resolución y tipo desde el primer video encontrado
        video_data = parse_video_filename(videos[0]) if videos else {"resolution": "1080p", "release_type": "BluRay"}

        # Verificar si algún video ya tiene subtítulo .es.srt
        has_sub = any(subtitle_exists(full_path, v) for v in videos)

        info = FolderInfo(
            folder_name=entry,
            folder_path=full_path,
            title=parsed["title"],
            year=parsed["year"],
            resolution=video_data["resolution"],
            release_type=video_data["release_type"],
            videos=videos,
            has_subtitle=has_sub,
        )
        folders.append(info)

    logger.info("Carpetas de media encontradas: %d", len(folders))
    return folders


def get_folder_info(folder_name: str) -> FolderInfo | None:
    """
    Retorna FolderInfo para una carpeta específica por su nombre.
    """
    media_root = get_media_root()
    full_path = os.path.join(media_root, folder_name)

    if not os.path.isdir(full_path):
        logger.warning("Carpeta no encontrada: '%s'", full_path)
        return None

    parsed = parse_folder_name(folder_name)
    if not parsed:
        logger.warning("Carpeta con formato inválido: '%s'", folder_name)
        return None

    videos = get_videos_in_folder(full_path)

    # Resolución y tipo desde el primer video encontrado
    video_data = parse_video_filename(videos[0]) if videos else {"resolution": "1080p", "release_type": "BluRay"}
    has_sub = any(subtitle_exists(full_path, v) for v in videos)

    info = FolderInfo(
        folder_name=folder_name,
        folder_path=full_path,
        title=parsed["title"],
        year=parsed["year"],
        resolution=video_data["resolution"],
        release_type=video_data["release_type"],
        videos=videos,
        has_subtitle=has_sub,
    )
    logger.info("FolderInfo cargado: '%s' — videos: %d", folder_name, len(videos))
    return info


def save_subtitle(folder_path: str, video_filename: str, content: bytes) -> str:
    """
    Guarda el subtítulo descargado con el mismo nombre del video + .es.srt
    Retorna la ruta del archivo guardado.
    """
    base = os.path.splitext(video_filename)[0]
    subtitle_filename = f"{base}.es.srt"
    subtitle_path = os.path.join(folder_path, subtitle_filename)

    try:
        with open(subtitle_path, "wb") as f:
            f.write(content)
        logger.info("Subtítulo guardado: '%s'", subtitle_path)
    except OSError as e:
        logger.error("Error al guardar subtítulo '%s': %s", subtitle_path, e)
        raise

    return subtitle_path


def list_srts_in_archive(content: bytes) -> list[str]:
    """
    Retorna los nombres de archivos .srt dentro de un ZIP o RAR.
    Detecta el formato por los magic bytes del contenido.
    """
    # ZIP: magic bytes PK (0x50 0x4B)
    if content[:2] == b'PK':
        try:
            import io
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                srts = [n for n in zf.namelist() if n.lower().endswith('.srt')]
                logger.info("ZIP — archivos .srt encontrados: %s", srts)
                return srts
        except zipfile.BadZipFile as e:
            logger.error("Error al leer ZIP: %s", e)
            return []

    # RAR: magic bytes Rar! (0x52 0x61 0x72 0x21)
    if content[:4] == b'Rar!' and _RARFILE_AVAILABLE:
        try:
            import io
            import tempfile
            # rarfile requiere un archivo en disco, no soporta BytesIO
            with tempfile.NamedTemporaryFile(suffix='.rar', delete=False) as tmp:
                tmp.write(content)
                tmp_path = tmp.name
            try:
                with rarfile.RarFile(tmp_path) as rf:
                    srts = [n for n in rf.namelist() if n.lower().endswith('.srt')]
                    logger.info("RAR — archivos .srt encontrados: %s", srts)
                    return srts
            finally:
                os.unlink(tmp_path)
        except Exception as e:
            logger.error("Error al leer RAR: %s", e)
            return []

    logger.warning("Formato de archivo no reconocido o rarfile no disponible")
    return []


def extract_srt_from_archive(content: bytes, srt_name: str) -> bytes | None:
    """
    Extrae el contenido de un .srt específico de un ZIP o RAR.
    Retorna los bytes del .srt o None si falla.
    """
    if content[:2] == b'PK':
        try:
            import io
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                data = zf.read(srt_name)
                logger.info("Extraído '%s' del ZIP — %d bytes", srt_name, len(data))
                return data
        except (zipfile.BadZipFile, KeyError) as e:
            logger.error("Error al extraer '%s' del ZIP: %s", srt_name, e)
            return None

    if content[:4] == b'Rar!' and _RARFILE_AVAILABLE:
        try:
            import tempfile
            with tempfile.NamedTemporaryFile(suffix='.rar', delete=False) as tmp:
                tmp.write(content)
                tmp_path = tmp.name
            try:
                with rarfile.RarFile(tmp_path) as rf:
                    data = rf.read(srt_name)
                    logger.info("Extraído '%s' del RAR — %d bytes", srt_name, len(data))
                    return data
            finally:
                os.unlink(tmp_path)
        except Exception as e:
            logger.error("Error al extraer '%s' del RAR: %s", srt_name, e)
            return None

    logger.error("No se pudo extraer '%s' — formato no soportado", srt_name)
    return None