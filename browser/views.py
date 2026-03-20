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
)
from browser.services.subx import (
    search_subtitles,
    search_by_preferred_user,
    search_with_fallback,
    download_subtitle,
)

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
    folder = get_folder_info(folder_name)
    if not folder:
        return render(request, "browser/error.html", {
            "message": f"Carpeta no encontrada o formato inválido: {folder_name}"
        }, status=404)

    logger.info("Detalle de carpeta: '%s' — videos: %d", folder_name, len(folder.videos))
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
    video_filename = request.GET.get("video", "").strip()
    keyword = request.GET.get("keyword", "").strip()

    folder = get_folder_info(folder_name)
    if not folder:
        return HttpResponse("<p class='text-danger'>Carpeta no encontrada.</p>", status=404)

    if not video_filename:
        return HttpResponse("<p class='text-warning'>Seleccioná un video primero.</p>")

    if video_filename not in folder.videos:
        logger.warning("Video '%s' no pertenece a la carpeta '%s'", video_filename, folder_name)
        return HttpResponse("<p class='text-danger'>Video inválido.</p>", status=400)

    sub_status = check_subtitle_status(folder.folder_path, video_filename)
    preferred_user = settings.SUBDIVX_PREFERRED_USER

    if not keyword:
        # Búsqueda solo dentro del usuario preferido con cascada tipo+resolución
        all_results = search_subtitles(folder.title)
        if not all_results:
            results, criteria = [], "none"
        elif preferred_user:
            user_result = search_by_preferred_user(
                all_results,
                preferred_user,
                folder.release_type,
                folder.resolution,
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
            "user+type+res": f"usuario preferido + {folder.release_type} + {folder.resolution}",
            "user+type":     f"usuario preferido + {folder.release_type}",
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

    # Renombrar .srt sin .es a .en.srt si existe
    renamed_to_english = rename_plain_srt_to_english(folder.folder_path, video_filename)

    # Limpiar carpeta antes de guardar
    deleted_files = clean_folder(folder.folder_path, video_filename)

    # Descargar subtítulo
    content = download_subtitle(subtitle_id)
    if not content:
        return HttpResponse(
            "<p class='text-danger'>Error al descargar el subtítulo. Intentá con otro.</p>",
            status=502
        )

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