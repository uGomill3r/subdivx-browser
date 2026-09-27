import json
import logging

from django.conf import settings
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

from series.services import renamer
from series.services import subtitles as series_subtitles

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


@require_GET
def suggest_title_view(request):
    """
    API: sugiere un título de búsqueda a partir de la carpeta seleccionada
    (detecta temporada + nombre de serie). El resultado es solo un punto de
    partida editable, no una búsqueda en sí.
    """
    path = request.GET.get("path", "").strip()
    if not path:
        return JsonResponse({"title": ""})

    title = series_subtitles.build_search_title(path)
    return JsonResponse({"title": title})


@require_GET
def subtitle_search_view(request):
    """
    API: busca subtítulos para Series contra la API directa de SubDivX
    (nunca subx-bridge, independientemente del proveedor configurado para
    Películas). Query params: title, keyword (opcional), free_query (opcional).
    """
    title = request.GET.get("title", "").strip()
    keyword = request.GET.get("keyword", "").strip()
    free_query = request.GET.get("free_query", "").strip()

    if not title and not free_query:
        return HttpResponseBadRequest("Falta 'title' o 'free_query'")

    results, matched_by = series_subtitles.search(title, keyword=keyword, free_query=free_query)
    logger.info(
        "Búsqueda de subtítulos (series) — title='%s' keyword='%s' free='%s' — criterio: %s — resultados: %d",
        title, keyword, free_query, matched_by, len(results),
    )
    return JsonResponse({
        "results": [r.__dict__ for r in results],
        "matched_by": matched_by,
    })


@require_POST
def subtitle_download_view(request):
    """
    API: descarga un subtítulo (o pack de temporada comprimido) por su ID y
    extrae/guarda su contenido en `path`. Body JSON: {subtitle_id, path}.
    No sobrescribe intencionalmente por nombre repetido — si ocurre, se
    registra un WARNING pero el archivo se guarda igual (queda listo para
    reordenar/renombrar en el explorador).
    """
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        logger.error("Body JSON inválido en subtitle_download_view: %s", e)
        return HttpResponseBadRequest("JSON inválido")

    subtitle_id = str(data.get("subtitle_id", "")).strip()
    path = data.get("path", "").strip()

    if not subtitle_id or not path:
        return JsonResponse({"success": False, "message": "Parámetros incompletos."}, status=400)

    safe_path = renamer.resolve_safe_path(path)
    if safe_path is None:
        return JsonResponse(
            {"success": False, "message": "Ruta inválida o fuera de la biblioteca de series."},
            status=400,
        )

    content = series_subtitles.download_subtitle(subtitle_id)
    if not content:
        return JsonResponse({"success": False, "message": "Error al descargar el subtítulo."}, status=502)

    saved_files = series_subtitles.extract_all_subtitles(content, safe_path)
    if not saved_files:
        return JsonResponse(
            {"success": False, "message": "No se pudieron extraer subtítulos del archivo descargado."},
            status=422,
        )

    logger.info("Descarga completada en '%s' — %d archivo(s)", safe_path, len(saved_files))
    return JsonResponse({
        "success": True,
        "message": f"{len(saved_files)} archivo(s) guardado(s). Ya podés reordenarlos y renombrarlos.",
        "files": saved_files,
    })