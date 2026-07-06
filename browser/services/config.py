import json
import logging
import os
from pathlib import Path

from django.conf import settings

logger = logging.getLogger(__name__)

# Ruta del archivo de configuración persistente
CONFIG_FILE = Path(settings.BASE_DIR) / "config.json"

# Claves soportadas y sus valores por defecto (fallback a settings)
_DEFAULTS = {
    "media_root": None,          # se resuelve desde settings en runtime
    "preferred_user": None,      # ídem
    "preferred_words": [],       # palabras extra para el filtro inicial
}

# Proveedores de API de subtítulos soportados
API_PROVIDER_SUBX = "subx"
API_PROVIDER_SUBX_BRIDGE = "subx_bridge"
VALID_API_PROVIDERS = {API_PROVIDER_SUBX, API_PROVIDER_SUBX_BRIDGE}


# Estructura por defecto de tipos y resoluciones con sus keywords de búsqueda
DEFAULT_RELEASE_TYPES = [
    {"name": "BluRay", "keywords": ["bluray", "blu-ray", "bdrip", "brip"]},
    {"name": "WEBRip", "keywords": ["webrip", "web-rip"]},
    {"name": "WEB-DL", "keywords": ["webdl", "web-dl", "web dl"]},
    {"name": "HDTV",   "keywords": ["hdtv"]},
]

DEFAULT_RESOLUTIONS = [
    {"name": "720p",  "keywords": ["720p", "720"]},
    {"name": "1080p", "keywords": ["1080p", "1080", "fhd"]},
    {"name": "2160p", "keywords": ["2160p", "2160", "4k", "uhd"]},
]


def _settings_defaults() -> dict:
    """Retorna valores por defecto tomados desde settings/env."""
    return {
        "media_root": settings.MEDIA_ROOT_PATH,
        "preferred_user": settings.SUBDIVX_PREFERRED_USER,
        "preferred_words": [],
        "media_root_options": [],   # lista de rutas predefinidas para el select
        "release_types": DEFAULT_RELEASE_TYPES,
        "resolutions": DEFAULT_RESOLUTIONS,
        "api_provider": API_PROVIDER_SUBX,
        "subx_bridge_url": settings.SUBX_BRIDGE_URL,
    }


def load_config() -> dict:
    """
    Carga la configuración desde config.json.
    Si el archivo no existe o está corrupto, retorna los defaults de settings.
    """
    defaults = _settings_defaults()

    if not CONFIG_FILE.exists():
        logger.info("config.json no encontrado — usando defaults de settings")
        return defaults

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Mezclar con defaults para keys faltantes
        config = {**defaults, **data}
        logger.info("config.json cargado — media_root: '%s', preferred_user: '%s', palabras: %d, opciones: %d",
                    config["media_root"], config["preferred_user"],
                    len(config["preferred_words"]), len(config["media_root_options"]))
        return config
    except (json.JSONDecodeError, OSError) as e:
        logger.error("Error al leer config.json: %s — usando defaults", e)
        return defaults


def save_config(
    media_root: str,
    preferred_user: str,
    preferred_words: list[str],
    release_types: list[str] | None = None,
    resolutions: list[str] | None = None,
    api_provider: str | None = None,
    subx_bridge_url: str | None = None,
) -> bool:
    """
    Persiste la configuración en config.json preservando media_root_options.
    Retorna True si se guardó correctamente.
    """
    defaults = _settings_defaults()
    existing = load_config()

    if api_provider is not None and api_provider not in VALID_API_PROVIDERS:
        logger.warning("api_provider inválido '%s' — se ignora y se mantiene el existente", api_provider)
        api_provider = None

    data = {
        "media_root": media_root.strip(),
        "preferred_user": preferred_user.strip(),
        "preferred_words": [w.strip() for w in preferred_words if w.strip()],
        "media_root_options": existing.get("media_root_options", []),
        "release_types": release_types if release_types is not None else existing.get("release_types", defaults["release_types"]),
        "resolutions": resolutions if resolutions is not None else existing.get("resolutions", defaults["resolutions"]),
        "api_provider": api_provider if api_provider is not None else existing.get("api_provider", defaults["api_provider"]),
        "subx_bridge_url": (subx_bridge_url.strip() if subx_bridge_url is not None else existing.get("subx_bridge_url", defaults["subx_bridge_url"])),
    }
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info(
            "config.json guardado — media_root: '%s', preferred_user: '%s', palabras: %s, tipos: %d, "
            "resoluciones: %d, proveedor: '%s'",
            data["media_root"], data["preferred_user"], data["preferred_words"],
            len(data["release_types"]), len(data["resolutions"]), data["api_provider"],
        )
        return True
    except OSError as e:
        logger.error("Error al guardar config.json: %s", e)
        return False


def get_media_root_options() -> list[str]:
    """Retorna las rutas predefinidas para el select de biblioteca."""
    config = load_config()
    return config.get("media_root_options", [])


def get_media_root() -> str:
    """Retorna la ruta de media activa (config.json > settings)."""
    config = load_config()
    return config["media_root"] or settings.MEDIA_ROOT_PATH


def get_preferred_user() -> str:
    """Retorna el usuario preferido activo (config.json > settings)."""
    config = load_config()
    return config["preferred_user"] or settings.SUBDIVX_PREFERRED_USER


def get_preferred_words() -> list[str]:
    """Retorna las palabras del filtro inicial definidas en config.json."""
    config = load_config()
    return config.get("preferred_words", [])


def get_release_types() -> list[dict]:
    """Retorna los tipos de release activos con sus keywords desde config.json."""
    config = load_config()
    return config.get("release_types", DEFAULT_RELEASE_TYPES)


def get_resolutions() -> list[dict]:
    """Retorna las resoluciones activas con sus keywords desde config.json."""
    config = load_config()
    return config.get("resolutions", DEFAULT_RESOLUTIONS)


def get_api_provider() -> str:
    """Retorna el proveedor de API activo ('subx' o 'subx_bridge')."""
    config = load_config()
    provider = config.get("api_provider", API_PROVIDER_SUBX)
    if provider not in VALID_API_PROVIDERS:
        logger.warning("api_provider desconocido en config.json ('%s') — usando '%s'", provider, API_PROVIDER_SUBX)
        return API_PROVIDER_SUBX
    return provider


def get_subx_bridge_url() -> str:
    """Retorna la URL base configurada para subx-bridge (config.json > settings)."""
    config = load_config()
    return config.get("subx_bridge_url") or settings.SUBX_BRIDGE_URL