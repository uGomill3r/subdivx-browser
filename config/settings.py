import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv("SECRET_KEY", "django-insecure-default")
DEBUG = os.getenv("DEBUG", "True") == "True"
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.staticfiles",
    "browser",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# Sin base de datos — solo filesystem y API calls
DATABASES = {}

LANGUAGE_CODE = "es-ar"
TIME_ZONE = "America/Lima"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "browser" / "static"]


# Configuración de la app
SUBX_API_KEY = os.getenv("SUBX_API_KEY", "")
SUBDIVX_PREFERRED_USER = os.getenv("SUBDIVX_PREFERRED_USER", "")
MEDIA_ROOT_PATH = os.getenv("MEDIA_ROOT", "/media/videos")

# subx-bridge: proveedor alternativo, autohospedado, que reemplaza a la SubX API
# consultando Subdivx de forma directa (https://github.com/fr0gb1t/subx-bridge).
# La URL no tiene un valor público fijo porque cada quien corre su propia instancia.
SUBX_BRIDGE_URL = os.getenv("SUBX_BRIDGE_URL", "")
SUBX_BRIDGE_API_KEY = os.getenv("SUBX_BRIDGE_API_KEY", "")

# Directorio del repo de subx-bridge en el filesystem de la Pi (contiene el
# .env y el docker-compose.yml). Lo usa la captura manual de cookie de
# Cloudflare para actualizar el .env y reiniciar el contenedor.
SUBX_BRIDGE_DIR = os.getenv("SUBX_BRIDGE_DIR", str(Path.home() / "subx-bridge"))

# User-Agent usado por Playwright al visitar subdivx.com durante la captura
# manual de cookie. Debe coincidir con SUBDIVX_USER_AGENT del .env de
# subx-bridge, o la cookie cf_clearance quedará asociada a un UA distinto
# del que usa el bridge para scrapear.
SUBX_BRIDGE_CF_USER_AGENT = os.getenv(
    "SUBDIVX_USER_AGENT",
    "Mozilla/5.0 (X11; Linux x86_64; rv:148.0) Gecko/20100101 Firefox/148.0",
)


VIDEO_EXTENSIONS = [".mp4", ".mkv"]

# Carpetas a excluir del escaneo (separadas por coma en .env)
_excluded = os.getenv("MEDIA_EXCLUDED_FOLDERS", "")
MEDIA_EXCLUDED_FOLDERS = {f.strip() for f in _excluded.split(",") if f.strip()}

# Carpeta y archivo donde se persisten los logs de la app.
# Guardarlos en disco es lo que permite mostrarlos luego en la vista /logs/.
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "subdivx-browser.log"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} — {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(LOG_FILE),
            "maxBytes": 2 * 1024 * 1024,  # 2 MB por archivo
            "backupCount": 3,
            "formatter": "verbose",
            "encoding": "utf-8",
        },
    },
    "root": {
        "handlers": ["console", "file"],
        "level": "DEBUG",
    },
}