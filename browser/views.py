import logging
from django.shortcuts import render
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt

from browser.services.filesystem import (
    list_media_folders,
    get_folder_info,
    save_subtitle,
    subtitle_exists,
)
from browser.services.subx import search_with_fallback, download_subtitle

logger = logging.getLogger(__name__)


def index(request: HttpRequest) -> HttpResponse:
    """Vista principal: lista de carpetas de media."""
    folders = list_media_folders()
    logger.info("Index cargado — carpetas: %d", len(folders))
    return render(request, "browser/index.html", {"folders": folders})


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


def search_subtitles(request: HttpRequest, folder_name: str) -> HttpResponse:
    """
    Busca subtítulos para un video seleccionado.
    Acepta parámetros GET: video (nombre de archivo), keyword (opcional).
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

    already_has_sub = subtitle_exists(folder.folder_path, video_filename)

    results, criteria = search_with_fallback(
        title=folder.title,
        release_type=folder.release_type,
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
        "already_has_sub": already_has_sub,
        "criteria_labels": {
            "user": "usuario preferido",
            "keyword": "palabra clave",
            "quality": "tipo de release",
            "all": "todos los disponibles",
            "none": "sin resultados",
        },
    }
    return render(request, "browser/partials/results.html", context)


@require_http_methods(["POST"])
def download_and_save(request: HttpRequest, folder_name: str) -> HttpResponse:
    """
    Descarga un subtítulo y lo guarda con el nombre correcto.
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

    content = download_subtitle(subtitle_id)
    if not content:
        return HttpResponse(
            "<p class='text-danger'>Error al descargar el subtítulo. Intentá con otro.</p>",
            status=502
        )

    try:
        saved_path = save_subtitle(folder.folder_path, video_filename, content)
    except OSError:
        return HttpResponse(
            "<p class='text-danger'>Error al guardar el subtítulo en disco.</p>",
            status=500
        )

    import os
    saved_filename = os.path.basename(saved_path)
    logger.info("Subtítulo guardado exitosamente: '%s'", saved_filename)

    return render(request, "browser/partials/success.html", {
        "saved_filename": saved_filename,
        "folder_name": folder_name,
    })
