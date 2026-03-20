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


def _settings_defaults() -> dict:
    """Retorna valores por defecto tomados desde settings/env."""
    return {
        "media_root": settings.MEDIA_ROOT_PATH,
        "preferred_user": settings.SUBDIVX_PREFERRED_USER,
        "preferred_words": [],
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
        logger.info("config.json cargado — media_root: '%s', preferred_user: '%s', palabras: %d",
                    config["media_root"], config["preferred_user"], len(config["preferred_words"]))
        return config
    except (json.JSONDecodeError, OSError) as e:
        logger.error("Error al leer config.json: %s — usando defaults", e)
        return defaults


def save_config(media_root: str, preferred_user: str, preferred_words: list[str]) -> bool:
    """
    Persiste la configuración en config.json.
    Retorna True si se guardó correctamente.
    """
    data = {
        "media_root": media_root.strip(),
        "preferred_user": preferred_user.strip(),
        "preferred_words": [w.strip() for w in preferred_words if w.strip()],
    }
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info("config.json guardado — media_root: '%s', preferred_user: '%s', palabras: %s",
                    data["media_root"], data["preferred_user"], data["preferred_words"])
        return True
    except OSError as e:
        logger.error("Error al guardar config.json: %s", e)
        return False


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
