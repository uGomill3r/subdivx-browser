import json
import logging

from django.conf import settings
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

from series.services import renamer

logger = logging.getLogger(__name__)


@require_GET
def index(request):
    """
    Vista principal de la sección Series: shell HTML con el explorador de
    carpetas. La navegación y el listado de archivos se resuelven client-side
    contra los endpoints JSON de abajo (igual que en el media-renamer original).
    """
    logger.info("Acceso a sección Series — raíz configurada: '%s'", settings.SERIES_ROOT)
    return render(request, "series/index.html", {
        "series_root": settings.SERIES_ROOT,
    })


@require_GET
def list_folders_view(request):
    """
    API: retorna las subcarpetas de `path` (query param), o de SERIES_ROOT
    si no se indica. Siempre 200 — una ruta inválida simplemente devuelve [].
    """
    path = request.GET.get("path", settings.SERIES_ROOT)
    subfolders = renamer.list_subfolders(path)
    return JsonResponse(subfolders, safe=False)


@require_GET
def list_files_view(request):
    """
    API: retorna videos y subtítulos presentes en `path` (query param).
    """
    path = request.GET.get("path", settings.SERIES_ROOT)
    files = renamer.list_files_in_path(path)
    return JsonResponse(files)


@require_POST
def rename_files_view(request):
    """
    API: ejecuta el renombrado por posición.
    Body JSON esperado: {action, path, video_files, sub_files}.
    Retorna 200 si success, 400 si falló la validación o el renombrado.
    """
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        logger.error("Body JSON inválido en rename_files_view: %s", e)
        return HttpResponseBadRequest("JSON inválido")

    action = data.get("action", "")
    path = data.get("path", "")
    video_files = data.get("video_files", [])
    sub_files = data.get("sub_files", [])

    result = renamer.rename_files(action, path, video_files, sub_files)
    status = 200 if result["success"] else 400
    return JsonResponse(result, status=status)
