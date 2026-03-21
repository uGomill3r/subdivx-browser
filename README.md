# SubDivX Browser

App Django 5.2 para buscar y descargar subtítulos desde SubDivX (vía SubX API) en una Raspberry Pi. Acceso desde red local via navegador.

## Requisitos

- Raspberry Pi OS
- Python 3.11+
- nginx
- `unrar` (para soporte de archivos RAR): `sudo apt install unrar -y`

## Instalación

### 1. Clonar el repositorio

```bash
git clone https://github.com/tu-usuario/subdivx-browser.git
cd subdivx-browser
```

### 2. Entorno virtual y dependencias

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

### 4. Archivos estáticos

```bash
python manage.py collectstatic --noinput
```

### 5. Servicio systemd

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

### 6. nginx como proxy

```bash
sudo apt install nginx -y
sudo rm /etc/nginx/sites-enabled/default
sudo nano /etc/nginx/sites-available/subdivx-browser
```

```nginx
server {
    listen 8002;
    server_name _;

    location /static/ {
        alias /home/pi/subdivx-browser/staticfiles/;
    }

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
pip install -r requirements.txt --index-url https://pypi.org/simple/
python manage.py collectstatic --noinput
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

- La resolución y el tipo se leen del nombre del archivo de video
- Si no hay tipo, se asume BluRay por defecto

## Búsqueda de subtítulos

La búsqueda usa título **y año** como parámetros a la API (el año filtra resultados correctamente en SubX).

### Búsqueda inicial automática (sin keyword):
1. Usuario preferido + tipo + resolución + palabras preferidas (todas las condiciones, AND)
2. Si no hay resultados → tipo + resolución sin usuario (automático, muestra aviso)
3. Si tampoco hay resultados → muestra formulario de keyword y botón "Ver todos"

### Con keyword manual:
- Busca en todos los resultados de la API por las palabras ingresadas (AND)
- Si no hay resultados con keyword → cae a tipo + resolución, luego todos los disponibles

### Ver todos:
- Disponible en cualquier momento, muestra todos los resultados sin filtrar

## Descarga de subtítulos

Los archivos descargados pueden estar comprimidos (ZIP o RAR):
- **Un solo .srt en el archivo**: se extrae y guarda automáticamente
- **Múltiples .srt**: se muestra un modal para elegir cuál guardar

Proceso al guardar:
1. Si existe `video.srt` → renombrar a `video.en.srt`
2. Limpiar carpeta: eliminar todo excepto `.mp4`, `.srt` y carpetas `subtitle/subtitles`
3. Guardar como `video.es.srt`

## Configuración desde la interfaz

Accesible desde el ícono ⚙ en la barra superior (`/settings/`). Permite cambiar sin reiniciar el servicio:

- **Ruta de la biblioteca**: seleccionable desde lista predefinida en `config.json`, o input libre
- **Usuario preferido**: usuario de SubDivX priorizado en la búsqueda inicial
- **Palabras del filtro inicial**: chips editables, se aplican como AND sobre usuario + tipo + resolución
- **Tipos de release**: chips editables con keywords de búsqueda configurables por tipo (click en el chip abre modal)
- **Resoluciones**: igual que tipos, con keywords editables por resolución

Los cambios se guardan en `config.json` (no incluido en el repo) y tienen prioridad sobre `.env`.

### Formato de config.json

```json
{
  "media_root": "/mnt/HDD/Descargas",
  "preferred_user": "TaMaBin",
  "preferred_words": ["LATINO"],
  "media_root_options": [
    "/mnt/HDD/Descargas",
    "/mnt/HDD/Library/Movies/"
  ],
  "release_types": [
    {"name": "BluRay",  "keywords": ["bluray", "blu-ray", "bdrip", "brip"]},
    {"name": "WEBRip",  "keywords": ["webrip", "web-rip"]},
    {"name": "WEB-DL",  "keywords": ["webdl", "web-dl", "web dl"]},
    {"name": "HDTV",    "keywords": ["hdtv"]}
  ],
  "resolutions": [
    {"name": "720p",  "keywords": ["720p", "720"]},
    {"name": "1080p", "keywords": ["1080p", "1080", "fhd"]},
    {"name": "2160p", "keywords": ["2160p", "2160", "4k", "uhd"]}
  ]
}
```

`media_root_options` se edita manualmente en el archivo. Si está vacío o ausente, se muestra un input de texto libre.

`release_types` y `resolutions` son editables desde la UI. Si no están en `config.json`, se usan los valores por defecto definidos en `config.py`.