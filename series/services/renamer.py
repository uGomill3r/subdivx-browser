import os
import logging
from django.conf import settings

logger = logging.getLogger(__name__)


def resolve_safe_path(path: str) -> str | None:
    """
    Resuelve `path` a una ruta absoluta y verifica que quede dentro de
    SERIES_ROOT (protección contra path traversal vía query params/body).
    Retorna la ruta resuelta o None si queda fuera de la raíz permitida.
    """
    series_root = os.path.realpath(settings.SERIES_ROOT)
    resolved = os.path.realpath(path)

    if resolved != series_root and not resolved.startswith(series_root + os.sep):
        logger.warning("Path fuera de SERIES_ROOT rechazado: '%s'", path)
        return None

    return resolved


def list_subfolders(path: str) -> list[str]:
    """
    Retorna las subcarpetas visibles (no ocultas) de `path`, ordenadas.
    Lista vacía si la ruta es inválida, está fuera de SERIES_ROOT o no es
    accesible.
    """
    safe_path = resolve_safe_path(path)
    if safe_path is None:
        return []

    try:
        subfolders = sorted(
            f for f in os.listdir(safe_path)
            if os.path.isdir(os.path.join(safe_path, f)) and not f.startswith(".")
        )
    except OSError as e:
        logger.error("Error al listar subcarpetas de '%s': %s", safe_path, e)
        return []

    logger.debug("Subcarpetas encontradas en '%s': %s", safe_path, subfolders)
    return subfolders


def list_files_in_path(path: str) -> dict:
    """
    Retorna los videos y subtítulos presentes en `path`, separados por tipo
    y ordenados alfabéticamente. Ignora archivos ocultos.
    Listas vacías si la ruta es inválida o inaccesible.
    """
    safe_path = resolve_safe_path(path)
    if safe_path is None:
        return {"video_files": [], "sub_files": []}

    video_files = []
    sub_files = []

    try:
        entries = sorted(os.listdir(safe_path))
    except OSError as e:
        logger.error("Error al listar archivos de '%s': %s", safe_path, e)
        return {"video_files": [], "sub_files": []}

    for entry in entries:
        if entry.startswith("."):
            continue
        if not os.path.isfile(os.path.join(safe_path, entry)):
            continue

        ext = os.path.splitext(entry)[1].lower()
        if ext in settings.VIDEO_EXTENSIONS:
            video_files.append(entry)
        elif ext in settings.SERIES_SUBTITLE_EXTENSIONS:
            sub_files.append(entry)

    logger.info(
        "Archivos listados en '%s' — videos: %d, subtítulos: %d",
        safe_path, len(video_files), len(sub_files),
    )
    return {"video_files": video_files, "sub_files": sub_files}


def rename_files(action: str, path: str, video_files: list[str], sub_files: list[str]) -> dict:
    """
    Renombra videos o subtítulos por posición (video[i] <-> sub[i]).

    - action == "rename_subtitles": cada subtítulo toma el nombre base del
      video correspondiente + sufijo ".es" antes de su propia extensión.
    - action == "rename_videos": cada video toma el nombre base del
      subtítulo correspondiente, conservando la extensión del video.

    Retorna {"success": bool, "message": str}.
    """
    safe_path = resolve_safe_path(path)
    if safe_path is None:
        return {"success": False, "message": "Ruta inválida o fuera de la biblioteca de series."}

    if action not in ("rename_subtitles", "rename_videos"):
        logger.warning("Acción de renombrado desconocida: '%s'", action)
        return {"success": False, "message": f"Acción desconocida: {action}"}

    if len(video_files) != len(sub_files):
        logger.warning(
            "Cantidad desigual de archivos en '%s' — videos: %d, subtítulos: %d",
            safe_path, len(video_files), len(sub_files),
        )
        return {"success": False, "message": "La cantidad de videos y subtítulos no coincide."}

    if not video_files:
        logger.warning("Renombrado solicitado sin archivos en '%s'", safe_path)
        return {"success": False, "message": "No hay archivos para renombrar."}

    renamed = []
    try:
        for video_name, sub_name in zip(video_files, sub_files):
            video_base = os.path.splitext(video_name)[0]
            sub_ext = os.path.splitext(sub_name)[1]

            if action == "rename_subtitles":
                new_name = f"{video_base}.es{sub_ext}"
                os.rename(os.path.join(safe_path, sub_name), os.path.join(safe_path, new_name))
                renamed.append((sub_name, new_name))
            else:  # rename_videos
                sub_base = os.path.splitext(sub_name)[0]
                video_ext = os.path.splitext(video_name)[1]
                new_name = f"{sub_base}{video_ext}"
                os.rename(os.path.join(safe_path, video_name), os.path.join(safe_path, new_name))
                renamed.append((video_name, new_name))
    except OSError as e:
        logger.error("Error al renombrar en '%s': %s", safe_path, e)
        return {"success": False, "message": f"Error al renombrar: {e}"}

    logger.info(
        "Renombrado '%s' completado en '%s' — %d archivos: %s",
        action, safe_path, len(renamed), renamed,
    )
    return {"success": True, "message": "Renombrado exitoso"}