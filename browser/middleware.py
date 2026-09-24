import threading

from django.core import signing

# Nombre de la cookie donde se persiste la biblioteca activa por navegador.
MEDIA_ROOT_COOKIE = "sdx_media_root"

# Salt de firma — distingue esta cookie de otras firmadas con la misma SECRET_KEY.
_SIGNING_SALT = "browser.media_root"

# La cookie dura un año; si vence, se vuelve al media_root de config.json.
_COOKIE_MAX_AGE = 60 * 60 * 24 * 365

# Almacenamiento por hilo para exponer el override de biblioteca desde la
# cookie a la capa de servicios, sin tener que pasar `request` por todos lados.
# Asume despliegue WSGI con un único worker (--workers 1).
_local = threading.local()


def get_current_media_root_override() -> str | None:
    """Retorna el override de media_root para la request actual, o None."""
    return getattr(_local, "media_root_override", None)


def set_media_root_cookie(response, media_root: str) -> None:
    """
    Adjunta a la respuesta una cookie firmada con la biblioteca activa.
    Firmada con SECRET_KEY: el cliente no puede modificar el valor.
    """
    response.set_signed_cookie(
        MEDIA_ROOT_COOKIE,
        media_root,
        salt=_SIGNING_SALT,
        max_age=_COOKIE_MAX_AGE,
        httponly=True,
        samesite="Lax",
    )


class MediaRootOverrideMiddleware:
    """
    Lee la cookie firmada `sdx_media_root` y deja su valor disponible para
    `config.get_media_root()` via thread-local. Si la cookie falta, está
    vencida o fue manipulada, el override queda en None y la app cae al
    media_root de config.json.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # get_signed_cookie devuelve `default` si la firma es inválida o la
        # cookie no existe. Con default=None no se propaga ninguna excepción.
        override = request.get_signed_cookie(
            MEDIA_ROOT_COOKIE, salt=_SIGNING_SALT, default=None
        )
        _local.media_root_override = override or None
        try:
            return self.get_response(request)
        finally:
            _local.media_root_override = None