import os
import re
import logging
from dataclasses import dataclass, field
from django.conf import settings

logger = logging.getLogger(__name__)

# Formato esperado: Título (año) [resolución] [tipo] ...
FOLDER_PATTERN = re.compile(
    r'^(?P<title>.+?)\s\((?P<year>\d{4})\)\s\[(?P<resolution>720p|1080p|2160p)\]\s\[(?P<type>BluRay|WEBRip|WEB-DL)\]',
    re.IGNORECASE,
)

# Carpetas de subtítulos que se conservan
SUBTITLE_FOLDERS = {"subtitle", "subtitles"}


@dataclass
class FolderInfo:
    folder_name: str
    folder_path: str
    title: str
    year: str
    resolution: str
    release_type: str  # BluRay / WEBRip / WEB-DL
    videos: list[str] = field(default_factory=list)
    has_subtitle: bool = False


def parse_folder_name(folder_name: str) -> dict | None:
    """
    Parsea el nombre de carpeta y retorna los campos extraídos.
    Retorna None si el formato no coincide.
    """
    match = FOLDER_PATTERN.match(folder_name)
    if not match:
        logger.debug("Carpeta sin formato reconocido: '%s'", folder_name)
        return None
    return match.groupdict()


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
    media_root = settings.MEDIA_ROOT_PATH

    try:
        entries = os.listdir(media_root)
    except OSError as e:
        logger.error("Error al leer MEDIA_ROOT '%s': %s", media_root, e)
        return []

    folders = []
    for entry in sorted(entries):
        full_path = os.path.join(media_root, entry)
        if not os.path.isdir(full_path):
            continue

        parsed = parse_folder_name(entry)
        if not parsed:
            continue

        videos = get_videos_in_folder(full_path)

        # Verificar si algún video ya tiene subtítulo .es.srt
        has_sub = any(subtitle_exists(full_path, v) for v in videos)

        info = FolderInfo(
            folder_name=entry,
            folder_path=full_path,
            title=parsed["title"],
            year=parsed["year"],
            resolution=parsed["resolution"],
            release_type=parsed["type"],
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
    media_root = settings.MEDIA_ROOT_PATH
    full_path = os.path.join(media_root, folder_name)

    if not os.path.isdir(full_path):
        logger.warning("Carpeta no encontrada: '%s'", full_path)
        return None

    parsed = parse_folder_name(folder_name)
    if not parsed:
        logger.warning("Carpeta con formato inválido: '%s'", folder_name)
        return None

    videos = get_videos_in_folder(full_path)
    has_sub = any(subtitle_exists(full_path, v) for v in videos)

    info = FolderInfo(
        folder_name=folder_name,
        folder_path=full_path,
        title=parsed["title"],
        year=parsed["year"],
        resolution=parsed["resolution"],
        release_type=parsed["type"],
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