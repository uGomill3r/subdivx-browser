# SubDivX Browser

App Django 5.2 para buscar y descargar subtítulos desde SubDivX (vía SubX API) en una Raspberry Pi. Acceso desde red local via navegador.

## Requisitos

- Raspberry Pi OS
- Python 3.11+
- nginx

## Instalación

### 1. Clonar el repositorio

```bash
git clone https://github.com/tu-usuario/subdivx-browser.git
cd subdivx-browser
```

### 2. Entorno virtual e dependencias

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt --index-url https://pypi.org/simple/
```

### 3. Configuración

```bash
cp .env.example .env
nano .env
```

Variables requeridas:

```
SECRET_KEY=cadena-larga-y-random
DEBUG=False
SUBX_API_KEY=tu_api_key
SUBDIVX_PREFERRED_USER=nombre_usuario_subdivx
MEDIA_ROOT=/ruta/a/tu/carpeta/de/videos
MEDIA_EXCLUDED_FOLDERS=carpeta1,carpeta2
```

### 4. Servicio systemd

```bash
sudo nano /etc/systemd/system/subdivx-browser.service
```

```ini
[Unit]
Description=SubDivX Browser
After=network.target

[Service]
User=pi
WorkingDirectory=/home/pi/subdivx-browser
ExecStart=/home/pi/subdivx-browser/venv/bin/gunicorn config.wsgi:application --workers 1 --worker-class gthread --threads 4 --bind 0.0.0.0:8001 --timeout 60 --keep-alive 5
Restart=on-failure
RestartSec=5
Environment=DJANGO_SETTINGS_MODULE=config.settings

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable subdivx-browser
sudo systemctl start subdivx-browser
```

### 5. nginx como proxy

```bash
sudo apt install nginx -y
sudo rm /etc/nginx/sites-enabled/default
sudo nano /etc/nginx/sites-available/subdivx-browser
```

```nginx
server {
    listen 8002;
    server_name _;

    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/subdivx-browser /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl enable nginx
sudo systemctl start nginx
```

Accedé desde cualquier dispositivo en la red local:

```
http://<ip-raspberry>:8002
```

## Actualizar

```bash
cd ~/subdivx-browser
git pull
sudo systemctl restart subdivx-browser
```

## Logs

```bash
# App
sudo journalctl -u subdivx-browser -f

# nginx
sudo journalctl -u nginx -f
```

## Formato de carpetas

```
Título (año) [resolución] [tipo opcional] ...
```

- La resolución y el tipo se leen del nombre del archivo de video si no están en la carpeta
- Si no hay tipo, se asume BluRay por defecto

## Búsqueda de subtítulos (cascada)

### Sin keyword (búsqueda inicial automática):
1. Usuario preferido + tipo + resolución + palabras preferidas (si están configuradas)
2. Usuario preferido + tipo + resolución
3. Usuario preferido + tipo
4. Usuario preferido (sin filtros)
5. → Si no hay resultados: muestra formulario de keyword

### Con keyword:
6. Palabra clave en descripción
7. Tipo + resolución (sin usuario)
8. Todos los disponibles

## Configuración desde la interfaz

La app incluye una vista de configuración accesible desde el ícono ⚙ en la barra superior (`/settings/`). Permite cambiar sin reiniciar el servicio:

- **Ruta de la biblioteca**: carpeta raíz donde están las películas/series
- **Usuario preferido**: usuario de SubDivX priorizado en la búsqueda inicial
- **Palabras del filtro inicial**: términos adicionales que se aplican sobre los resultados del usuario preferido (ej: `LATINO`, `ESPAÑOL`)

Los cambios se guardan en `config.json` en la raíz del proyecto y tienen prioridad sobre las variables del `.env`. Si `config.json` no existe, se usan los valores del `.env`.

## Lógica al descargar un subtítulo

1. Si existe `video.srt` → renombrar a `video.en.srt`
2. Limpiar carpeta: eliminar todo excepto `.mp4`, `.srt` y carpetas `subtitle/subtitles`
3. Descargar subtítulo de SubX API
4. Guardar como `video.es.srt`