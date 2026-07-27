# SubDivX Browser — Contexto del proyecto

## Descripción
App Django 5.2 para buscar y descargar subtítulos desde SubDivX (vía SubX API) en una Raspberry Pi. Acceso desde red local via navegador web con diseño responsivo.

---

## Stack técnico
- **Django 5.2** — framework principal
- **Gunicorn** — servidor WSGI (gthread, 1 worker, 4 threads)
- **nginx** — proxy reverso + sirve archivos estáticos
- **HTMX** — interactividad sin JS pesado
- **Bootstrap 5** — UI responsiva
- **SQLite** — no se usa, sin base de datos
- **SubX API** — `https://subx-api.duckdns.org/api` — API no oficial de SubDivX
- **rarfile** — soporte para descomprimir RAR (requiere `unrar` en el sistema)

---

## Infraestructura en Raspberry Pi
- **OS**: Raspberry Pi OS
- **Usuario**: `pi`
- **Proyecto**: `/home/pi/subdivx-browser`
- **Venv**: `/home/pi/subdivx-browser/venv`
- **Media**: `/mnt/HDD/Descargas/` y `/mnt/HDD/Library/Movies/` (HDD externo USB)
- **Puertos**:
  - nginx: `8002` (público, acceso desde red local)
  - Gunicorn: `8001` (interno)
- **Acceso**: `https://pibox.lan:8002`
- **Hostname**: `pibox`
- **Dominio local**: `pibox.lan` → `192.168.11.120` (configurado en Pi-hole)
- **HTTPS**: certificado mkcert para `pibox.lan`, CA instalada en iOS y macOS

### Permisos importantes
- `/home/pi` debe tener `o+x` para que nginx pueda servir estáticos:
  ```bash
  chmod o+x /home/pi
  ```

### Servicios systemd
```bash
sudo systemctl status subdivx-browser   # Gunicorn
sudo systemctl status nginx
sudo journalctl -u subdivx-browser -f   # logs app
sudo journalctl -u nginx -f             # logs nginx
```

### Actualizar en Raspberry
```bash
cd ~/subdivx-browser
git pull
pip install -r requirements.txt --index-url https://pypi.org/simple/
python manage.py collectstatic --noinput
sudo systemctl restart subdivx-browser
```

---

## Estructura del proyecto
```
subdivx_browser/
├── .env                          ← variables de entorno (no en repo)
├── .env.example                  ← plantilla
├── config.json                   ← config runtime (no en repo)
├── manage.py
├── start.sh                      ← arranque Gunicorn
├── requirements.txt
├── README.md
├── subdivx_browser_context.md    ← este archivo
├── config/
│   ├── settings.py
│   ├── urls.py                   ← include("browser.urls", namespace="browser")
│   └── wsgi.py
└── browser/
    ├── views.py
    ├── urls.py
    ├── services/
    │   ├── config.py             ← lectura/escritura config.json, fallback a .env
    │   ├── filesystem.py         ← parseo carpetas/videos, extracción ZIP/RAR
    │   └── subx.py               ← cliente SubX API, lógica de filtros y búsqueda
    ├── static/
    │   └── browser/
    │       └── apple-touch-icon.png  ← ícono 180x180 para iOS/iPadOS
    ├── templatetags/
    │   └── browser_extras.py     ← filtro get_item para dicts en templates
    └── templates/browser/
        ├── base.html             ← layout, fuentes Inter+DM Mono, topbar con ⚙
        ├── index.html            ← carga lazy via HTMX
        ├── folder.html           ← pestañas por video, búsqueda automática, spinner
        ├── settings.html         ← configuración: ruta, usuario, palabras, tipos, resoluciones
        ├── error.html
        └── partials/
            ├── folder_list.html  ← lista con pestañas sin/con subtítulo
            ├── results.html      ← resultados, modal descripción, Ver todos
            ├── success.html      ← confirmación descarga, vuelve al inicio
            ├── select_srt.html   ← modal selección .srt en archivo comprimido
            └── keyword_form.html ← búsqueda por keyword (AND multi-palabra)
```

---

## Variables de entorno (.env)
```
SECRET_KEY=cadena-larga-y-random
DEBUG=True
SUBX_API_KEY=tu_api_key
SUBDIVX_PREFERRED_USER=TaMaBin
MEDIA_ROOT=/mnt/HDD/Descargas
MEDIA_EXCLUDED_FOLDERS=ZenZone
```

---

## config.json (no en repo, editar en la Pi)
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

- `media_root_options`: lista de rutas para el select en settings. Se edita manualmente. Si está vacío muestra input libre.
- `preferred_words`: chips editables desde la UI. Se aplican como filtro AND sobre usuario + tipo + resolución.
- `release_types`: lista de objetos `{name, keywords}`. Editables desde la UI — chips con modal de keywords por tipo.
- `resolutions`: igual que release_types. Editables desde la UI.
- Tiene prioridad sobre `.env`. Si no existe, usa valores del `.env` y defaults de `config.py`.

---

## Tipografía
- **Inter** (wght 400/600/700/800) — títulos, botones, headers, brand
- **DM Mono** (wght 300/400/500) — body, inputs, tabs, código
- Cargadas desde Google Fonts con `rel="preload"` no bloqueante

---

## Favicon e ícono
- **Favicon**: SVG inline en `<link rel="icon">` — letras Sx sobre fondo oscuro + `favicon.ico` en `/` via nginx
- **Apple touch icon**: PNG 180×180 en `browser/static/browser/apple-touch-icon.png`, servido también desde `/apple-touch-icon.png` y `/apple-touch-icon-precomposed.png` via nginx

## PWA / Íconos
- **apple-touch-icon.png**: PNG 180×180 en `browser/static/browser/`, servido también desde `/apple-touch-icon.png` y `/apple-touch-icon-precomposed.png` via nginx
- **favicon.ico**: en `browser/static/browser/`, servido desde `/favicon.ico` via nginx
- Con HTTPS + dominio `pibox.lan` Safari iOS muestra el ícono correctamente en favoritos — no se necesita manifest ni Service Worker
- `.local` no funciona para íconos en favoritos de Safari iOS aunque HTTPS esté configurado; `.lan` vía Pi-hole sí funciona

---

## Diseño visual
- Tema oscuro con variables CSS en `:root`
- `--accent: #e8c840` (dorado), `--text: #d4d8e8`, `--text-muted: #6b7294`
- `.section-header`: color `#8899bb` (azul-gris), border-bottom `var(--accent-dim)`

---

## Formato de carpetas de media
Solo se requiere `Título (año)` — resolución y tipo se leen del archivo de video.

```
Título (año) [resolución opcional] [tipo opcional] ...
```

- **Resolución** extraída del nombre del archivo de video (720p / 1080p / 2160p)
- **Tipo** extraído del nombre del archivo (BluRay / WEBRip / WEB-DL / HDTV)
- Default resolución: `1080p` / Default tipo: `BluRay`
- Extensión soportada: `.mp4`

---

## Cascada de búsqueda de subtítulos

La búsqueda envía `title` **y** `year` como parámetros separados a la API SubX (confirmado que filtra correctamente).

### Búsqueda inicial automática (sin keyword):
1. Usuario preferido + tipo + resolución + preferred_words (AND, todas las condiciones)
2. Si no hay resultados → tipo + resolución sin usuario (automático, muestra aviso en UI con criterio `no_user+type+res`)
3. Si tampoco hay resultados → muestra formulario keyword + botón "Ver todos"

### Con keyword manual:
- Busca en todos los resultados de la API (AND entre palabras)
- Si no hay resultados con keyword → tipo + resolución → todos los disponibles

### Ver todos:
- Disponible siempre, salta toda la cascada, muestra los 20 resultados de la API

### Criterios reportados en UI (`criteria`):
| Valor | Descripción |
|-------|-------------|
| `user+type+res+words` | usuario + tipo + resolución + palabras preferidas |
| `user+type+res` | usuario + tipo + resolución |
| `no_user+type+res` | sin usuario preferido — tipo + resolución |
| `type+res` | tipo + resolución (sin usuario configurado) |
| `keyword` | búsqueda por keyword manual |
| `all` | todos los disponibles |
| `none` | sin resultados en la API |
| `needs_keyword` | sin resultados — pide keyword |

---

## Lógica de filtros en subx.py

### `search_by_preferred_user`
Estricto: aplica usuario + tipo + resolución + palabras en una sola pasada. Retorna `None` si alguna condición falla — sin cascada interna.

### `search_with_fallback`
Solo para búsquedas con keyword manual:
1. keyword en todos los resultados
2. tipo + resolución (si keyword no da resultados)
3. todos los resultados

### `filter_by_quality` / `filter_by_resolution`
Leen las keywords desde `config.json` via `get_release_types()` / `get_resolutions()`. Los dicts `QUALITY_KEYWORDS` y `RESOLUTION_KEYWORDS` en el módulo son solo fallback/referencia.

### `_keywords_for(name, config_list, fallback)`
Helper que busca las keywords configuradas para un nombre dado. Si no está en config, usa el dict de fallback.

---

## Descarga de subtítulos
Los archivos descargados son ZIP o RAR (raramente .srt directo).

Detección por magic bytes:
- ZIP: `PK` (0x50 0x4B)
- RAR: `Rar!` (0x52 0x61 0x72 0x21)

Flujo:
1. Descarga → detecta formato
2. Si comprimido con **1 srt** → extrae y guarda directo
3. Si comprimido con **múltiples srt** → modal de selección (`select_srt.html`)
4. Si selección: extrae el elegido
5. Renombrar `video.srt` → `video.en.srt` si existe
6. Limpiar carpeta (conserva `.mp4`, `.srt`, carpetas `subtitle/subtitles`)
7. Guardar como `video.es.srt`

---

## settings_view — patrón PRG
Usa Post/Redirect/Get: tras guardar exitosamente redirige a `?saved=1`. El GET lee ese parámetro y activa el banner de éxito. Evita reenvío del formulario al refrescar.

## settings.html — chips con keywords
- `preferred_words`: chips simples separados por coma en campo hidden
- `release_types` y `resolutions`: chips con contador de keywords. Click abre modal con sub-chips de keywords editables. Se serializa como JSON en el campo hidden. El POST lo deserializa con `json.loads`.

---

## nginx
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

---

## HTTPS en red local

### Stack
- **mkcert** — genera certificados firmados por una CA local
- **Pi-hole** — DNS local para resolver `pibox.lan` → `192.168.11.120`
- **nginx** — sirve HTTPS en puerto 8002 con el certificado mkcert

### Certificados
- `/etc/nginx/certs/pibox.lan.pem` — certificado
- `/etc/nginx/certs/pibox.lan-key.pem` — clave privada
- CA root en `$(mkcert -CAROOT)/rootCA.pem`
- Expiran: junio 2028

### Renovar certificado
```bash
mkcert pibox.lan
sudo cp ~/pibox.lan.pem /etc/nginx/certs/
sudo cp ~/pibox.lan-key.pem /etc/nginx/certs/
sudo chmod 600 /etc/nginx/certs/pibox.lan*
sudo systemctl reload nginx
```

### Instalar CA en nuevo dispositivo iOS
```bash
cp $(mkcert -CAROOT)/rootCA.pem ~/subdivx-browser/staticfiles/rootCA.pem
```
Safari iOS → `http://192.168.11.120:8002/static/rootCA.pem` → instalar perfil → Ajustes → General → Información → Configuración de confianza de certificados → activar.

### Por qué pibox.lan y no pibox.local
Safari iOS trata `.local` diferente a otros dominios locales y no muestra íconos en favoritos aunque HTTPS esté configurado. Con `.lan` vía Pi-hole Safari iOS muestra el ícono correctamente en favoritos sin necesidad de manifest ni Service Worker.

### Lo que NO es necesario para el ícono en favoritos
Después de pruebas exhaustivas se confirmó que con HTTPS + `pibox.lan` el ícono funciona solo con `apple-touch-icon.png`. Los siguientes archivos fueron probados y descartados como innecesarios:
- `manifest.webmanifest`
- `sw.js` / `registerSW.js`
- `icon-192.png` / `icon-512.png`

---

## settings.py — configuración relevante
```python
STATICFILES_DIRS = [BASE_DIR / "browser" / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
STATIC_URL = "/static/"
VIDEO_EXTENSIONS = [".mp4"]
```

---

## Archivos estáticos PWA (opcionales, no requeridos para ícono)
Los siguientes archivos existen en `browser/static/browser/` pero no se referencian desde el código — pueden eliminarse sin impacto:
- `sw.js`, `registerSW.js`, `manifest.webmanifest`, `icon-192.png`, `icon-512.png`

---

## Bugs corregidos en esta sesión
- `filesystem.py`: `_RESOLUTION_PATTERN` y `_TYPE_PATTERN` usaban comillas simples en raw strings haciendo que `\b` se interpretara como backspace (`\x08`). Los patrones nunca matcheaban — resolución y tipo siempre caían al default.
- `views.py` (`download_and_save`): `rename_plain_srt_to_english` y `clean_folder` se llamaban dos veces consecutivas.
- `settings.html`: `onclick="addWord()"` → `addChip('word')` tras unificar el script JS.
- `settings.html`: comillas en `onclick="removeChip()"` mal escapadas generaban `removeChip(,0)`.
- `settings.html`: separador `\n` en atributos `value=""` normalizado a espacio por el browser (HTML5). Cambiado a coma para `preferred_words`; JSON para `release_types` y `resolutions`.

---

## Pendientes / mejoras posibles
- Soporte para más extensiones de video (.mkv, .avi)
- Caché de resultados SubX API por título+año (evitar ~2s en cada entrada a carpeta)
- Botón "Actualizar biblioteca" para invalidar caché manualmente
- Indicador visual de subtítulo `.en.srt` en la lista de carpetas