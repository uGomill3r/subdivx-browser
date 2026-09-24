import threading

# Almacenamiento por hilo para exponer el override de biblioteca desde la
# sesión a la capa de servicios, sin tener que pasar `request` por todos lados.
# Asume despliegue WSGI con un único worker (--workers 1).
_local = threading.local()


def get_current_media_root_override() -> str | None:
    """Retorna el override de media_root para la request actual, o None."""
    return getattr(_local, "media_root_override", None)


class MediaRootOverrideMiddleware:
    """
    Lee la preferencia de biblioteca guardada en la sesión (`media_root_override`)
    y la deja disponible para `config.get_media_root()` via thread-local.

    Permite que el switch del index cambie la biblioteca activa durante la
    sesión, sin modificar config.json.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        override = request.session.get("media_root_override")
        _local.media_root_override = override
        try:
            return self.get_response(request)
        finally:
            _local.media_root_override = None