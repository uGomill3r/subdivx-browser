# SubDivX Browser

App Django 5.2 para buscar y descargar subtítulos desde SubDivX (vía SubX API) en una Raspberry Pi. Acceso desde red local via navegador.

## Requisitos

- Raspberry Pi OS
- Python 3.11+
- nginx
- `unrar` (para soporte de archivos RAR): `sudo apt install unrar -y`
- `mkcert` — certificados HTTPS para red local
- Pi-hole — DNS local (para dominio `pibox.lan`)

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
cp .env.sample .env
nano .env
```

`.env.sample` incluye las variables mínimas y opcionales. Las obligatorias son `SECRET_KEY`, `SUBX_API_KEY` y `MEDIA_ROOT`; el resto se puede dejar con valores por defecto.

```ini
# ── Obligatorias ────────────────────────────────────────────────────────────
SECRET_KEY=cadena-larga-y-random
DEBUG=False
SUBX_API_KEY=tu_api_key
SUBDIVX_PREFERRED_USER=nombre_usuario_subdivx
MEDIA_ROOT=/ruta/a/tu/carpeta/de/videos
MEDIA_EXCLUDED_FOLDERS=carpeta1,carpeta2

# ── Opcionales — proveedor subx-bridge ─────────────────────────────────────
# (https://github.com/fr0gb1t/subx-bridge), seleccionable en Configuración.
SUBX_BRIDGE_URL=http://tu-host-o-ip:8787
SUBX_BRIDGE_API_KEY=una_de_las_claves_definidas_en_SUBX_API_KEYS_del_bridge

# ── Opcionales — renovación interactiva de cookie de Cloudflare ────────────
# (requiere Playwright instalado, ver sección subx-bridge)
SUBX_BRIDGE_DIR=/home/pi/subx-bridge
SUBDIVX_USER_AGENT=Mozilla/5.0 (X11; Linux x86_64; rv:148.0) Gecko/20100101 Firefox/148.0

# ── Opcionales — botón "mover a biblioteca" en las tarjetas del índice ─────
MOVE_SOURCE_PATH=/mnt/HDD/Descargas
MOVE_DEST_PATH=/mnt/HDD/Library/Movies

# ── Opcionales — CA bundle para que requests confíe en subx-bridge ─────────
# (ver sección subx-bridge → paso 3)
REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
```

El proveedor de API activo (SubX o subx-bridge) se elige en la vista de **Configuración** y se guarda en `config.json`. Si elegís subx-bridge, la URL de tu instancia también se puede editar ahí; la API key siempre se toma de la variable de entorno `SUBX_BRIDGE_API_KEY`.

**Sobre `config.json`:** el repo no incluye `config.json` (está en `.gitignore`), sino `config.json.sample`. Copialo al primer arranque:

```bash
cp config.json.sample config.json
```

Sin él, la app arranca con los defaults de `settings.py` y no verás `media_root_options` (el switch de biblioteca). Ver "Formato de config.json" más abajo.

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

### 6. Certificado HTTPS con mkcert

```bash
# Instalar mkcert
sudo apt install libnss3-tools -y
curl -Lo mkcert https://github.com/FiloSottile/mkcert/releases/latest/download/mkcert-v1.4.4-linux-arm
chmod +x mkcert
sudo mv mkcert /usr/local/bin/

# Crear CA local y certificado
mkcert -install
mkcert pibox.lan

# Mover certificados
sudo mkdir -p /etc/nginx/certs
sudo cp ~/pibox.lan.pem /etc/nginx/certs/
sudo cp ~/pibox.lan-key.pem /etc/nginx/certs/
sudo chmod 600 /etc/nginx/certs/*
```

**Instalar la CA en iOS:**
```bash
cp $(mkcert -CAROOT)/rootCA.pem ~/subdivx-browser/staticfiles/rootCA.pem
```
Desde el iPhone en Safari: `http://192.168.11.120:8002/static/rootCA.pem` → instalar perfil → Ajustes → General → Información → Configuración de confianza de certificados → activar la CA de mkcert.

**Instalar la CA en macOS:**
```bash
scp pi@192.168.11.120:/home/pi/.local/share/mkcert/rootCA.pem ~/Desktop/
sudo security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain ~/Desktop/rootCA.pem
```

**Dominio local en Pi-hole:**
Local DNS → DNS Records → agregar `pibox.lan` → `192.168.11.120`

### 7. nginx como proxy

```bash
sudo apt install nginx -y
sudo rm /etc/nginx/sites-enabled/default
sudo nano /etc/nginx/sites-available/subdivx-browser
```

```nginx
server {
    listen 8002 ssl;
    server_name pibox.lan;

    ssl_certificate     /etc/nginx/certs/pibox.lan.pem;
    ssl_certificate_key /etc/nginx/certs/pibox.lan-key.pem;

    # Íconos servidos desde la raíz (requerido por Safari iOS)
    location = /apple-touch-icon.png {
        alias /home/pi/subdivx-browser/staticfiles/browser/apple-touch-icon.png;
    }

    location = /apple-touch-icon-precomposed.png {
        alias /home/pi/subdivx-browser/staticfiles/browser/apple-touch-icon.png;
    }

    location = /favicon.ico {
        alias /home/pi/subdivx-browser/staticfiles/browser/favicon.ico;
    }

    # Archivos estáticos
    location /static/ {
        alias /home/pi/subdivx-browser/staticfiles/;
        types {
            application/manifest+json  webmanifest;
        }
    }

    # App Django via Gunicorn
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
https://pibox.lan:8002
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
- Extensiones de video soportadas: `.mp4`, `.mkv`

## Búsqueda de subtítulos

La búsqueda usa título **y año** como parámetros a la API (el año filtra resultados correctamente en SubX). Si con el año de la carpeta no hay resultados, se reintenta automáticamente **sin año** antes de pasar al siguiente paso: cubre casos donde el año del archivo no coincide con el año del subtítulo publicado (por ejemplo, `McLaren (2016)` en la carpeta vs. `McLaren (2017)` en Subdivx). Cuando se descarta el año, se muestra un badge ámbar al lado del criterio.

Hay 4 formas de buscar, disponibles como botones/formularios debajo de los resultados (y también, las que aplican, en el panel de "sin resultados del usuario preferido"):

### Búsqueda inicial automática (sin keyword):
1. Título + año → si la API no devuelve nada, reintento sin año (badge ámbar "sin filtro de año")
2. Usuario preferido + tipo + resolución + palabras preferidas (todas las condiciones, AND)
3. Si no hay resultados → tipo + resolución sin usuario (automático, muestra aviso)
4. Si tampoco hay resultados → muestra formulario de keyword, botón "Ver todos" y botón "+ Búsqueda libre"

### Con keyword manual:
- Busca en todos los resultados de la API por las palabras ingresadas (AND)
- Si no hay resultados con keyword → cae a tipo + resolución, luego todos los disponibles

### Ver todos:
- Disponible en cualquier momento, muestra todos los resultados sin filtrar
- Aplica el mismo reintento sin año que la búsqueda automática

### Búsqueda libre:
- Disponible en cualquier momento junto a las otras opciones ("+ Búsqueda libre")
- También aparece directamente en el panel de "sin resultados" (`criteria == "none"`) cuando la API no devolvió nada ni siquiera sin año
- Es una búsqueda **nueva e independiente**: las palabras ingresadas se mandan directo a la API como término de búsqueda, sin usar título, año, tipo, resolución ni usuario preferido del video/carpeta
- No tiene cascada de fallback — o hay resultados para esas palabras, o se muestra "sin resultados"
- Útil para casos donde el nombre de la carpeta no coincide bien con el título real (ediciones, nombres alternativos, franquicias, etc.)

## Descarga de subtítulos

Los archivos descargados pueden estar comprimidos (ZIP o RAR):
- **Un solo .srt en el archivo**: se extrae y guarda automáticamente
- **Múltiples .srt**: se muestra un modal para elegir cuál guardar

Proceso al guardar:
1. Si existe `video.srt` → renombrar a `video.en.srt`
2. Limpiar carpeta: eliminar todo excepto video (`.mp4`/`.mkv`), `.srt` y carpetas `subtitle/subtitles`
3. Guardar como `video.es.srt`

## Mover a biblioteca

Cada tarjeta de película en el índice puede mostrar un botón (ícono de flecha, Bootstrap Icons) para mover la carpeta completa desde la carpeta de descargas activa hacia `MOVE_DEST_PATH` (por ejemplo, `Library/Movies`), conservando el nombre de carpeta.

- Solo aparece cuando la `media_root` activa coincide exactamente con `MOVE_SOURCE_PATH`; no tiene sentido (ni se permite) moverla si ya estás viendo la biblioteca de destino.
- Pide confirmación antes de mover (`hx-confirm` de HTMX).
- Si el destino ya tiene una carpeta con ese nombre, o hay un error de filesystem, se vuelve a renderizar la lista completa con el mensaje de error en la parte superior.
- Al mover con éxito, se reemplaza el parcial de la lista entera (la tarjeta desaparece y los contadores de las pestañas "Sin subtítulo" / "Con subtítulo" se recalculan solos).
- Si era la última carpeta de la biblioteca activa, se redirige a `/` con el header `HX-Redirect` (sin quedar en una vista vacía).

## Switch de biblioteca

Cuando `media_root_options` en `config.json` tiene 2 o más rutas, el index muestra un switch al lado del título "Biblioteca" para cambiar entre ellas sin pasar por Configuración.

- **2 opciones**: toggle con las dos rutas (segmented control, la activa resaltada).
- **3 o más**: botones `◀ ▶` con la ruta activa en el medio; van rotando por la lista.
- Se muestra solo el último segmento del path (`/mnt/HDD/Descargas` → `Descargas`); el completo aparece en el tooltip.
- La elección se guarda **por navegador** en una cookie firmada con `SECRET_KEY` (`sdx_media_root`, duración 1 año), no en `config.json`. Cada dispositivo puede estar viendo una biblioteca distinta.
- Si la cookie se borra o vence, la app cae al `media_root` de `config.json`.
- El servidor solo acepta rutas que estén en `media_root_options` (no se puede forzar por POST una ruta arbitraria).
- Al cambiar, la lista se recarga automáticamente via HTMX, sin recargar la página.

## Panel de logs en la app

Además de los logs vía `journalctl` (para debugging de infraestructura), la app expone un visor propio en `/logs/` (ícono de lista en la barra superior), pensado para revisar actividad sin acceso SSH:

- Lee `logs/subdivx-browser.log` (rotación automática a 2 MB, hasta 3 backups).
- Filtro por **nivel mínimo** (`DEBUG` a `CRITICAL`, o "Todos") y por **cantidad de líneas** (100 a 5000) a mostrar desde el final del archivo.
- Muestra las líneas más recientes primero, coloreadas por severidad (rojo para ERROR/CRITICAL, ámbar para WARNING).
- Indica cuántas líneas coinciden con el filtro vs. cuántas se están mostrando.

## Instalación como app (PWA)

El proyecto incluye manifest (`manifest.webmanifest`), service worker mínimo y set de íconos (`apple-touch-icon`, `icon-192`, `icon-512`) para poder "instalar" la app en la pantalla de inicio de un celular (modo `standalone`, sin barra de navegador), tanto en iOS como Android, una vez servida por HTTPS con el certificado de `mkcert` instalado en el dispositivo (ver paso 6 de instalación).

## Configuración desde la interfaz

Accesible desde el ícono de engranaje (Bootstrap Icons) en la barra superior (`/settings/`). Permite cambiar sin reiniciar el servicio:

- **Ruta de la biblioteca**: seleccionable desde lista predefinida en `config.json`, o input libre
- **Usuario preferido**: usuario de SubDivX priorizado en la búsqueda inicial
- **Palabras del filtro inicial**: chips editables, se aplican como AND sobre usuario + tipo + resolución
- **Tipos de release**: chips editables con keywords de búsqueda configurables por tipo (click en el chip abre modal)
- **Resoluciones**: igual que tipos, con keywords editables por resolución
- **Proveedor de API**: SubX o subx-bridge (si es subx-bridge, se puede configurar la URL de la instancia)
- **Cookie de Cloudflare**: botón de renovación interactiva cuando el proveedor es subx-bridge

Los cambios se guardan en `config.json` (no incluido en el repo, ver `config.json.sample`) y tienen prioridad sobre `.env`.

Para cambiar la biblioteca activa sin entrar a Configuración, ver la sección "Switch de biblioteca".

### Tema claro / oscuro

Botón con ícono de sol/luna (Bootstrap Icons) en la barra superior, agrupado junto a logs y configuración. Alterna entre tema oscuro (por defecto) y tema claro; la preferencia se guarda en el navegador (`localStorage`), no requiere reiniciar el servicio.

### Iconografía

Todos los íconos de navegación (barra superior: logs, configuración, tema; y accesos directos en `logs.html`/`settings.html`: volver a configuración, actualizar, ver logs, mensajes de error) usan [Bootstrap Icons](https://icons.getbootstrap.com/) vía CDN, reemplazando los emojis previos para una apariencia más consistente y profesional.

### Formato de config.json

El repo trae `config.json.sample` como plantilla. En la Pi, copialo a `config.json` y editalo:

```bash
cp config.json.sample config.json
```

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
  ],
  "api_provider": "subx",
  "subx_bridge_url": ""
}
```

- `media_root_options`: lista de rutas para el select en settings y para el switch del index. Se edita manualmente. Si está vacío o ausente, se muestra un input de texto libre en settings y no aparece el switch.
- `preferred_words`: chips editables desde la UI. Se aplican como filtro AND sobre usuario + tipo + resolución.
- `release_types`: lista de objetos `{name, keywords}`. Editables desde la UI — chips con modal de keywords por tipo.
- `resolutions`: igual que release_types. Editables desde la UI.
- `api_provider`: `"subx"` o `"subx_bridge"`.
- Tiene prioridad sobre `.env`. Si no existe, usa valores del `.env` y defaults de `config.py`.

## Proveedor alternativo: subx-bridge

Además de SubX API, la app soporta [subx-bridge](https://github.com/fr0gb1t/subx-bridge) como proveedor alternativo: un bridge HTTP autohospedado que consulta Subdivx de forma directa (sin depender del uptime de la SubX API pública). El proveedor activo se elige en **Configuración**, sin reiniciar el servicio.

### 1. Desplegar subx-bridge con Docker en la Pi

```bash
git clone https://github.com/fr0gb1t/subx-bridge.git
cd subx-bridge
```

Conseguí las cookies de sesión de Subdivx desde un navegador logueado (DevTools → pestaña Network → copiar el header `Cookie` del request principal a subdivx.com, y el `User-Agent` de ese mismo navegador).

Editá el `.env` (copiado de `.env.sample`):

```
SUBX_API_KEYS=una-clave-secreta-propia
SUBDIVX_CF_CLEARANCE=valor_de_cf_clearance
SUBDIVX_SDX=valor_de_sdx
SUBDIVX_USER_AGENT=el mismo user-agent del navegador usado para las cookies
LOG_LEVEL=INFO
```

**Importante**: el `docker-compose.yml` del repo trae los valores hardcodeados en vez de referenciar el `.env`. Hay que editarlo para que use variables:

```yaml
services:
  subx-bridge:
    build: .
    container_name: subx-bridge
    environment:
      SUBX_API_KEYS: "${SUBX_API_KEYS}"
      SUBDIVX_CF_CLEARANCE: "${SUBDIVX_CF_CLEARANCE}"
      SUBDIVX_SDX: "${SUBDIVX_SDX}"
      SUBDIVX_USER_AGENT: "${SUBDIVX_USER_AGENT}"
      LOG_LEVEL: "${LOG_LEVEL}"
    ports:
      - "8787:8787"
    restart: unless-stopped
```

```bash
docker compose up -d --build
curl http://127.0.0.1:8787/health
```

### 2. Exponer con nginx + dominio `.lan`

Pi-hole ya ocupa los puertos 80 y 443 (`pihole-FTL`), así que no se puede usar ese esquema para el bridge; se eligió un puerto propio (8443), igual que `pibox.lan` usa 8002.

```bash
mkcert subxbridge.lan   # sin sudo — con el mismo usuario que corre nginx/verificará el cert
```

```nginx
server {
    listen 8443 ssl;
    server_name subxbridge.lan;

    ssl_certificate     /etc/nginx/certs/subxbridge.lan.pem;
    ssl_certificate_key /etc/nginx/certs/subxbridge.lan-key.pem;

    location / {
        proxy_pass http://127.0.0.1:8787;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/subxbridge.lan /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl restart nginx
```

Agregá `subxbridge.lan` en Pi-hole (Local DNS → DNS Records) apuntando a la IP de la Pi.

**Ojo con mkcert y `sudo`**: si generás el certificado con `sudo mkcert ...`, queda firmado por la CA de `root`, no la de tu usuario (`mkcert -CAROOT` difiere entre `root` y `pi`). Generá el cert como el mismo usuario cuya CA ya está instalada y de la que vas a verificar, o vas a tener un mismatch de `issuer`.

### 3. Que Python confíe en el certificado

`requests` (usado por subdivx-browser) no usa el CA bundle del sistema por defecto, sino el de `certifi`. Agregá al `.env` de subdivx-browser:

```
REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
```

y asegurate de que la CA de mkcert esté instalada en ese bundle del sistema:

```bash
sudo cp "$(mkcert -CAROOT)/rootCA.pem" /usr/local/share/ca-certificates/mkcert-rootCA.crt
sudo update-ca-certificates
```

### 4. Configurar subdivx-browser

En su `.env`:

```
SUBX_BRIDGE_URL=https://subxbridge.lan:8443
SUBX_BRIDGE_API_KEY=una-clave-secreta-propia   # debe coincidir con SUBX_API_KEYS del bridge
```

Reiniciá el servicio, entrá a **Configuración**, elegí "subx-bridge" como proveedor y verificá con el botón de test de conexión (hace `/health` + una búsqueda de prueba).

### Mantenimiento: renovación de cookie desde la propia app

La cookie `SUBDIVX_CF_CLEARANCE` expira periódicamente (Cloudflare). En vez de tener que repetir el paso 1 a mano desde un navegador externo, la vista de **Configuración** (con subx-bridge seleccionado) incluye un botón **"Renovar cookie de Cloudflare"** que resuelve el challenge sin salir de la app:

1. Al hacer click, el servidor abre un navegador headless (Playwright/Chromium) contra `subdivx.com` y empieza a transmitir capturas de pantalla en vivo (polling cada ~0.4s) a la UI.
2. El usuario hace click sobre la imagen mostrada, en el lugar donde aparece el checkbox del challenge (Turnstile); el frontend traduce esas coordenadas al viewport real (1280×800) del navegador headless.
3. En cuanto Cloudflare emite la cookie `cf_clearance`, la app la escribe (junto con `sdx` y el User-Agent) directamente en el `.env` de subx-bridge y reinicia el contenedor (`docker compose restart`) automáticamente.
4. Si nadie interactúa, la captura se cancela sola a los 2 minutos (timeout de seguridad); también se puede cancelar manualmente en cualquier momento.

Esto requiere que `subdivx-browser` corra en la misma máquina donde vive el repo de subx-bridge (o con acceso a su ruta), configurado vía `SUBX_BRIDGE_DIR`, y que Playwright con Chromium esté instalado en el entorno de subdivx-browser (`playwright install chromium`).