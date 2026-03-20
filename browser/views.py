import os
import logging
from django.shortcuts import render
from django.http import HttpRequest, HttpResponse
from django.views.decorators.http import require_http_methods
from django.conf import settings

from browser.services.filesystem import (
    list_media_folders,
    get_folder_info,
    save_subtitle,
    subtitle_exists,
    check_subtitle_status,
    rename_plain_srt_to_english,
    clean_folder,
    list_srts_in_archive,
    extract_srt_from_archive,
)
from browser.services.subx import (
    search_subtitles,
    search_by_preferred_user,
    search_with_fallback,
    download_subtitle,
)
from browser.services.config import load_config, save_config, get_preferred_user, get_media_root_options
logger = logging.getLogger(__name__)


def index(request: HttpRequest) -> HttpResponse:
    """
    Vista principal: renderiza la página vacía de inmediato.
    La lista de carpetas se carga via HTMX en un request separado.
    """
    logger.info("Index cargado")
    return render(request, "browser/index.html")


def folder_list(request: HttpRequest) -> HttpResponse:
    """
    Retorna la lista de carpetas como HTML parcial para HTMX.
    Es el único punto donde se lee el disco para el índice.
    """
    folders = list_media_folders()
    logger.info("Lista de carpetas cargada — total: %d", len(folders))
    return render(request, "browser/partials/folder_list.html", {"folders": folders})


def folder_detail(request: HttpRequest, folder_name: str) -> HttpResponse:
    """
    Detalle de una carpeta: muestra los archivos de video y permite
    seleccionar uno para buscar subtítulos.
    """
    import time
    t0 = time.time()
    folder = get_folder_info(folder_name)
    t1 = time.time()
    if not folder:
        return render(request, "browser/error.html", {
            "message": f"Carpeta no encontrada o formato inválido: {folder_name}"
        }, status=404)

    t2 = time.time()
    logger.info(
        "Detalle de carpeta: '%s' — get_folder_info: %.3fs — render: %.3fs — total: %.3fs",
        folder_name, t1 - t0, t2 - t1, t2 - t0
    )
    return render(request, "browser/folder.html", {"folder": folder})


def search_subtitles_view(request: HttpRequest, folder_name: str) -> HttpResponse:
    """
    Busca subtítulos para un video seleccionado.
    Parámetros GET: video (nombre de archivo), keyword (opcional).

    Flujo sin keyword:
      1. usuario + tipo + resolución
      2. usuario + tipo
      3. usuario sin filtros
      → si ninguno: pide keyword

    Flujo con keyword:
      Cascada completa incluyendo keyword, tipo+res y todos.

    Responde con HTML parcial para HTMX.
    """
    import time
    t0 = time.time()

    video_filename = request.GET.get("video", "").strip()
    keyword = request.GET.get("keyword", "").strip()

    folder = get_folder_info(folder_name)
    t1 = time.time()
    if not folder:
        return HttpResponse("<p class='text-danger'>Carpeta no encontrada.</p>", status=404)

    if not video_filename:
        return HttpResponse("<p class='text-warning'>Seleccioná un video primero.</p>")

    if video_filename not in folder.videos:
        logger.warning("Video '%s' no pertenece a la carpeta '%s'", video_filename, folder_name)
        return HttpResponse("<p class='text-danger'>Video inválido.</p>", status=400)

    sub_status = check_subtitle_status(folder.folder_path, video_filename)
    preferred_user = get_preferred_user()

    if not keyword:
        # Búsqueda solo dentro del usuario preferido con cascada tipo+resolución
        all_results = search_subtitles(folder.title)
        t2 = time.time()
        logger.info("TIMING search — get_folder_info: %.3fs — API call: %.3fs", t1 - t0, t2 - t1)
        if not all_results:
            results, criteria = [], "none"
        elif preferred_user:
            from browser.services.config import get_preferred_words
            user_result = search_by_preferred_user(
                all_results,
                preferred_user,
                folder.release_type,
                folder.resolution,
                get_preferred_words(),
            )
            if user_result:
                results, criteria = user_result
            else:
                # Sin resultados del usuario → pedir keyword
                results, criteria = [], "needs_keyword"
        else:
            # Sin usuario configurado → cascada completa sin keyword
            results, criteria = search_with_fallback(
                title=folder.title,
                release_type=folder.release_type,
                resolution=folder.resolution,
            )
    else:
        # Con keyword → cascada completa
        results, criteria = search_with_fallback(
            title=folder.title,
            release_type=folder.release_type,
            resolution=folder.resolution,
            keyword=keyword,
        )

    logger.info(
        "Búsqueda completada — video: '%s' — criterio: %s — resultados: %d",
        video_filename, criteria, len(results)
    )

    context = {
        "folder": folder,
        "video_filename": video_filename,
        "results": results,
        "criteria": criteria,
        "sub_status": sub_status,
        "criteria_labels": {
            "user+type+res+words": f"usuario preferido + {folder.release_type} + {folder.resolution} + palabras preferidas",
            "user+type+res": f"usuario preferido + {folder.release_type} + {folder.resolution}",
            "user+type":     f"usuario preferido + {folder.release_type}",
            "user+words":    "usuario preferido + palabras preferidas",
            "user":          "usuario preferido",
            "keyword":       "palabra clave",
            "type+res":      f"{folder.release_type} + {folder.resolution}",
            "all":           "todos los disponibles",
            "none":          "sin resultados",
            "needs_keyword": "sin resultados del usuario preferido",
        },
    }
    return render(request, "browser/partials/results.html", context)


@require_http_methods(["POST"])
def download_and_save(request: HttpRequest, folder_name: str) -> HttpResponse:
    """
    Descarga un subtítulo, renombra .srt a .en.srt si existe,
    limpia la carpeta y guarda el nuevo .es.srt.
    Parámetros POST: subtitle_id, video_filename.
    """
    subtitle_id = request.POST.get("subtitle_id", "").strip()
    video_filename = request.POST.get("video_filename", "").strip()

    folder = get_folder_info(folder_name)
    if not folder:
        return HttpResponse("<p class='text-danger'>Carpeta no encontrada.</p>", status=404)

    if not subtitle_id or not video_filename:
        return HttpResponse("<p class='text-warning'>Parámetros incompletos.</p>", status=400)

    if video_filename not in folder.videos:
        logger.warning("Video '%s' inválido para carpeta '%s'", video_filename, folder_name)
        return HttpResponse("<p class='text-danger'>Video inválido.</p>", status=400)

    # Descargar archivo (puede ser .srt directo, ZIP o RAR)
    content = download_subtitle(subtitle_id)
    if not content:
        return HttpResponse(
            "<p class='text-danger'>Error al descargar el subtítulo. Intentá con otro.</p>",
            status=502
        )

    # Detectar si es archivo comprimido
    is_zip = content[:2] == b'PK'
    is_rar = content[:4] == b'Rar!'

    if is_zip or is_rar:
        srts = list_srts_in_archive(content)
        if not srts:
            return HttpResponse(
                "<p class='text-danger'>El archivo comprimido no contiene subtítulos .srt.</p>",
                status=422
            )
        if len(srts) == 1:
            # Un solo .srt — extraer y procesar directo
            srt_content = extract_srt_from_archive(content, srts[0])
            if not srt_content:
                return HttpResponse(
                    "<p class='text-danger'>Error al extraer el subtítulo del archivo.</p>",
                    status=500
                )
            content = srt_content
        else:
            # Múltiples .srt — mostrar modal de selección sin tocar el disco todavía
            import base64
            archive_b64 = base64.b64encode(content).decode()
            logger.info("Múltiples .srt en archivo — mostrando selector: %s", srts)
            return render(request, "browser/partials/select_srt.html", {
                "srts": srts,
                "archive_b64": archive_b64,
                "folder_name": folder_name,
                "video_filename": video_filename,
            })
    else:
        # Contenido directo (ya es .srt)
        logger.info("Archivo descargado directo como .srt — ID: %s", subtitle_id)

    # Renombrar .srt sin .es a .en.srt si existe (solo si vamos a guardar)
    renamed_to_english = rename_plain_srt_to_english(folder.folder_path, video_filename)

    # Limpiar carpeta antes de guardar
    deleted_files = clean_folder(folder.folder_path, video_filename)

    # Renombrar .srt sin .es a .en.srt si existe
    renamed_to_english = rename_plain_srt_to_english(folder.folder_path, video_filename)

    # Limpiar carpeta antes de guardar
    deleted_files = clean_folder(folder.folder_path, video_filename)

    # Guardar .es.srt
    try:
        saved_path = save_subtitle(folder.folder_path, video_filename, content)
    except OSError:
        return HttpResponse(
            "<p class='text-danger'>Error al guardar el subtítulo en disco.</p>",
            status=500
        )

    saved_filename = os.path.basename(saved_path)
    logger.info("Proceso completo para '%s' — guardado: '%s'", video_filename, saved_filename)

    return render(request, "browser/partials/success.html", {
        "saved_filename": saved_filename,
        "folder_name": folder_name,
        "renamed_to_english": renamed_to_english,
        "deleted_files": deleted_files,
    })


@require_http_methods(["POST"])
def select_and_save(request: HttpRequest, folder_name: str) -> HttpResponse:
    """
    Recibe la selección del usuario de un .srt dentro de un archivo comprimido,
    extrae el archivo elegido y lo guarda como .es.srt.
    Parámetros POST: srt_name, video_filename, archive_b64.
    """
    import base64

    srt_name = request.POST.get("srt_name", "").strip()
    video_filename = request.POST.get("video_filename", "").strip()
    archive_b64 = request.POST.get("archive_b64", "").strip()

    folder = get_folder_info(folder_name)
    if not folder:
        return HttpResponse("<p class='text-danger'>Carpeta no encontrada.</p>", status=404)

    if not srt_name or not video_filename or not archive_b64:
        return HttpResponse("<p class='text-warning'>Parámetros incompletos.</p>", status=400)

    if video_filename not in folder.videos:
        logger.warning("Video '%s' inválido para carpeta '%s'", video_filename, folder_name)
        return HttpResponse("<p class='text-danger'>Video inválido.</p>", status=400)

    try:
        content = base64.b64decode(archive_b64)
    except Exception as e:
        logger.error("Error al decodificar archivo comprimido: %s", e)
        return HttpResponse("<p class='text-danger'>Error al procesar el archivo.</p>", status=500)

    srt_content = extract_srt_from_archive(content, srt_name)
    if not srt_content:
        return HttpResponse(
            "<p class='text-danger'>Error al extraer el subtítulo seleccionado.</p>",
            status=500
        )

    renamed_to_english = rename_plain_srt_to_english(folder.folder_path, video_filename)
    deleted_files = clean_folder(folder.folder_path, video_filename)

    try:
        saved_path = save_subtitle(folder.folder_path, video_filename, srt_content)
    except OSError:
        return HttpResponse(
            "<p class='text-danger'>Error al guardar el subtítulo en disco.</p>",
            status=500
        )

    saved_filename = os.path.basename(saved_path)
    logger.info("Selección procesada para '%s' — srt: '%s' — guardado: '%s'",
                video_filename, srt_name, saved_filename)

    return render(request, "browser/partials/success.html", {
        "saved_filename": saved_filename,
        "folder_name": folder_name,
        "renamed_to_english": renamed_to_english,
        "deleted_files": deleted_files,
    })


@require_http_methods(["GET", "POST"])
def settings_view(request: HttpRequest) -> HttpResponse:
    """
    Vista de configuración: permite cambiar la ruta de la biblioteca
    y las palabras del filtro por defecto.
    GET: muestra el formulario con la config actual.
    POST: valida y guarda la nueva configuración.
    """
    success = False
    errors = []

    if request.method == "POST":
        media_root = request.POST.get("media_root", "").strip()
        preferred_user = request.POST.get("preferred_user", "").strip()
        words_raw = request.POST.get("preferred_words", "").strip()
        preferred_words = [w.strip() for w in words_raw.splitlines() if w.strip()]

        # Validar que la ruta exista
        if not media_root:
            errors.append("La ruta de la biblioteca no puede estar vacía.")
        elif not os.path.isdir(media_root):
            errors.append(f"La ruta '{media_root}' no existe o no es una carpeta.")

        if not errors:
            ok = save_config(media_root, preferred_user, preferred_words)
            if ok:
                success = True
                logger.info(
                    "Configuración guardada — media_root: '%s', preferred_user: '%s', palabras: %d",
                    media_root, preferred_user, len(preferred_words)
                )
            else:
                errors.append("Error al guardar la configuración. Revisá los permisos del archivo.")
                logger.error("Fallo al guardar config.json desde la vista de settings")

        config = {
            "media_root": media_root,
            "preferred_user": preferred_user,
            "preferred_words_text": "\n".join(preferred_words),
        }
    else:
        raw = load_config()
        config = {
            "media_root": raw["media_root"],
            "preferred_user": raw["preferred_user"],
            "preferred_words_text": "\n".join(raw.get("preferred_words", [])),
        }
        logger.info("Vista de configuración cargada")

    return render(request, "browser/settings.html", {
        "config": config,
        "success": success,
        "errors": errors,
        "media_root_options": get_media_root_options(),
    })