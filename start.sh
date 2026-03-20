#!/bin/bash
# Arranca la app con Gunicorn en puerto 8001 (interno)
# El acceso externo se hace via nginx en puerto 8002
# Ejecutar desde el directorio raíz del proyecto

export DJANGO_SETTINGS_MODULE=config.settings

cd "$(dirname "$0")"

gunicorn config.wsgi:application \
  --workers 1 \
  --worker-class gthread \
  --threads 4 \
  --bind 0.0.0.0:8001 \
  --timeout 60 \
  --keep-alive 5 \
  --access-logfile - \
  --error-logfile - \
  --log-level info