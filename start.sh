#!/bin/bash
# Arranca la app con Gunicorn — 1 worker (1 usuario simultáneo)
# Ejecutar desde el directorio raíz del proyecto

export DJANGO_SETTINGS_MODULE=config.settings

cd "$(dirname "$0")"

gunicorn config.wsgi:application \
  --workers 1 \
  --threads 1 \
  --bind 0.0.0.0:8001 \
  --timeout 60 \
  --keep-alive 2 \
  --worker-connections 10 \
  --access-logfile - \
  --error-logfile - \
  --log-level info
