import os
import re
import logging
from pathlib import Path
from dataclasses import dataclass, field
from django.conf import settings

logger = logging.getLogger(__name__)

# Formato esperado: Título (año) [resolución] [tipo] ...
FOLDER_PATTERN = re.compile(
    r'^(?P<title>.+?)\s\((?P<year>\d{4})\)\s\[(?P<resolution>720p|1080p|2160p)\]\s\[(?P<type>BluRay|WEBRip|WEB-DL)\]',
    re.IGNORECASE,
)


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


def subtitle_exists(folder_path: str, video_filename: str) -> bool:
    """
    Verifica si ya existe un subtítulo .es.srt para el video dado.
    """
    base = os.path.splitext(video_filename)[0]
    subtitle_path = os.path.join(folder_path, f"{base}.es.srt")
    return os.path.isfile(subtitle_path)


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

        # Verificar si algún video ya tiene subtítulo
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
