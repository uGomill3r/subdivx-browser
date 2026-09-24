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
- **Sin base de datos** — solo filesystem y API calls
- **Cookie firmada** — la biblioteca activa se guarda por navegador en una cookie firmada con `SECRET_KEY` (no se usan sesiones de Django)
- **SubX API** — `https://subx-api.duckdns.org/api` — API no oficial de SubDivX
- **subx-bridge** — proveedor alternativo autohospedado (opcional)
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
├── .env.sample                   ← plantilla
├── config.json                   ← config runtime (no en repo, ver .sample)
├── config.json.sample            ← plantilla de config runtime
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
    ├── middleware.py             ← MediaRootOverrideMiddleware + cookie firmada
    ├── services/
    │   ├── config.py             ← lectura/escritura config.json, fallback a .env
    │   ├── filesystem.py         ← parseo carpetas/videos, extracción ZIP/RAR
    │   ├── subx.py               ← cliente SubX API, lógica de filtros y búsqueda
    │   ├── subx_bridge.py        ← cliente del proveedor alternativo
    │   ├── subtitle_types.py     ← dataclass SubtitleResult + mapeo
    │   └── cf_cookie_capture.py  ← captura interactiva de cookie de Cloudflare
    ├── static/
    │   └── browser/
    │       └── apple-touch-icon.png  ← ícono 180x180 para iOS/iPadOS
    ├── templatetags/
    │   └── browser_extras.py     ← filtro get_item para dicts en templates
    └── templates/browser/
        ├── base.html             ← layout, fuentes Inter+DM Mono, topbar con íconos
        ├── index.html            ← carga lazy via HTMX + switch de biblioteca
        ├── folder.html           ← pestañas por video, búsqueda automática, spinner
        ├── settings.html         ← configuración: ruta, usuario, palabras, tipos, resoluciones
        ├── error.html
        ├── logs.html             ← visor de logs con filtro por nivel
        └── partials/
            ├── folder_list.html  ← lista con pestañas sin/con subtítulo, contadores
            ├── folder_card.html  ← tarjeta de carpeta, botón "mover a biblioteca"
            ├── results.html      ← resultados, modal descripción, Ver todos, badge sin año
            ├── success.html      ← confirmación descarga, vuelve al inicio
            ├── select_srt.html   ← modal selección .srt en archivo comprimido
            ├── keyword_form.html ← búsqueda por keyword (AND multi-palabra)
            ├── free_search_form.html ← búsqueda libre (término directo a la API)
            └── api_test_result.html  ← resultado del test de conexión a la API
```

---

## Variables de entorno (.env)
```
SECRET_KEY=cadena-larga-y-random
DEBUG=False
SUBX_API_KEY=tu_api_key
SUBDIVX_PREFERRED_USER=TaMaBin
MEDIA_ROOT=/mnt/HDD/Descargas
MEDIA_EXCLUDED_FOLDERS=ZenZone
SUBX_BRIDGE_URL=https://subxbridge.lan:8443
SUBX_BRIDGE_API_KEY=una-clave-secreta
SUBX_BRIDGE_DIR=/home/pi/subx-bridge
SUBDIVX_USER_AGENT=Mozilla/5.0 ...
MOVE_SOURCE_PATH=/mnt/HDD/Descargas
MOVE_DEST_PATH=/mnt/HDD/Library/Movies
REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
```

---

## config.json (no en repo, plantilla en config.json.sample)
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

- `media_root_options`: lista de rutas para el select en settings y para el switch del index. Se edita manualmente. Si está vacío o ausente, se muestra input libre en settings y no aparece el switch.
- `preferred_words`: chips editables desde la UI. Se aplican como filtro AND sobre usuario + tipo + resolución.
- `release_types`: lista de objetos `{name, keywords}`. Editables desde la UI — chips con modal de keywords por tipo.
- `resolutions`: igual que release_types. Editables desde la UI.
- `api_provider`: `"subx"` o `"subx_bridge"`.
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
- `--accent: #e8c840` (dorado), `--text: #f2f3fa`, `--text-muted: #e7e9f5`
- `.section-header`: color `var(--accent)`, border-bottom `var(--accent-dim)`
- `.criteria-badge`: píldora con borde `accent-dim`, texto `accent`
- `.criteria-badge-warn`: píldora ámbar (`#d9a441`) para el aviso de "sin filtro de año"

---

## Formato de carpetas de media
Solo se requiere `Título (año)` — resolución y tipo se leen del archivo de video.

```
Título (año) [resolución opcional] [tipo opcional] ...
```

- **Resolución** extraída del nombre del archivo de video (720p / 1080p / 2160p)
- **Tipo** extraído del nombre del archivo (BluRay / WEBRip / WEB-DL / HDTV)
- Default resolución: `1080p` / Default tipo: `BluRay`
- Extensiones soportadas: `.mp4`, `.mkv`

---

## Switch de biblioteca

El index permite alternar la biblioteca activa sin pasar por Configuración, cuando `media_root_options` tiene 2+ rutas.

### Flujo
1. `index` pasa `media_root_options` y `current_media_root` al template.
2. El template renderiza:
   - **2 opciones** → segmented control con dos botones, la activa resaltada.
   - **3+ opciones** → botones `◀ ▶` con la ruta activa en el medio (rotación circular).
3. Click → `POST /switch-media-root/` con el path elegido.
4. `switch_media_root_view` valida que el path esté en `media_root_options` (rechaza con 400 si no), setea la cookie firmada `sdx_media_root` y responde JSON.
5. El frontend actualiza el estado visual y dispara `htmx.ajax` a `folder_list` para recargar el listado.

### Persistencia: cookie firmada
- Nombre: `sdx_media_root`. Firma con `SECRET_KEY` + salt `browser.media_root`. Duración 1 año. `HttpOnly`, `SameSite=Lax`.
- **No se usan sesiones de Django**: el proyecto no tiene base de datos, y configurar `SESSION_ENGINE` con `signed_cookies` seguía dando 500 al guardar. La cookie firmada evita todo el framework de sesiones.
- El valor de la cookie **no es manipulable** por el cliente (cualquier modificación invalida la firma y `get_signed_cookie` devuelve `default=None`).

### Middleware
`browser/middleware.py`:
- `MediaRootOverrideMiddleware` lee la cookie y la expone via `thread_local` (`get_current_media_root_override()`).
- `set_media_root_cookie(response, path)` adjunta la cookie firmada a una respuesta.
- `config.get_media_root()` consulta el thread-local primero; solo acepta el override si el path está en `media_root_options` (defensa adicional).

### Prioridad de `get_media_root()`
1. Override de cookie (si el path está en `media_root_options`)
2. `config.json` → `media_root`
3. `settings.MEDIA_ROOT_PATH` (env)

---

## Cascada de búsqueda de subtítulos

La búsqueda envía `title` **y** `year` como parámetros separados a la API SubX.

### Reintento sin año
Si la búsqueda con `(title, year)` no devuelve resultados y la carpeta tiene año, se reintenta automáticamente con `(title, "")`. Cubre casos donde el año del archivo no coincide con el año del subtítulo publicado (ej: `McLaren (2016)` en la carpeta vs. `McLaren (2017)` en Subdivx). Cuando se descarta el año, se setea `year_filter_dropped = True` y se muestra un badge ámbar al lado del criterio en `results.html`.

Se aplica en **dos lugares** de `search_subtitles_view`:
- Búsqueda automática inicial (rama `else`)
- Ver todos (`show_all=1`)

No se aplica en la rama `keyword` (`search_with_fallback` sigue pasando `year` a la API).

### Búsqueda inicial automática (sin keyword):
1. `search_subtitles(title, year)` → si vacío y hay año, `search_subtitles(title, "")` (marca `year_filter_dropped`)
2. Usuario preferido + tipo + resolución + preferred_words (AND, todas las condiciones)
3. Si no hay resultados → tipo + resolución sin usuario (automático, muestra aviso en UI con criterio `no_user+type+res`)
4. Si tampoco hay resultados → muestra formulario keyword + "Ver todos" + "+ Búsqueda libre"

### Con keyword manual:
- Busca en todos los resultados de la API (AND entre palabras)
- Si no hay resultados con keyword → tipo + resolución → todos los disponibles

### Ver todos:
- Disponible siempre, salta toda la cascada, muestra los 20 resultados de la API
- Aplica el mismo reintento sin año que la búsqueda automática

### Búsqueda libre:
- Disponible en el pie de resultados como "+ Búsqueda libre"
- **También se muestra directamente cuando `criteria == "none"`** (la API no devolvió nada ni siquiera sin año) — antes solo se mostraba en `free_none`
- Es nueva e independiente: las palabras ingresadas van directo a la API como término de búsqueda, sin usar título/año/tipo/resolución/usuario del video

### Criterios reportados en UI (`criteria`):
| Valor | Descripción |
|-------|-------------|
| `user+type+res+words` | usuario + tipo + resolución + palabras preferidas |
| `user+type+res` | usuario + tipo + resolución |
| `no_user+type+res` | sin usuario preferido — tipo + resolución |
| `type+res` | tipo + resolución (sin usuario configurado) |
| `keyword` | búsqueda por keyword manual |
| `all` | todos los disponibles |
| `none` | sin resultados en la API (ni siquiera sin año) |
| `needs_keyword` | sin resultados del usuario preferido — pide keyword |
| `free` | búsqueda libre con resultados |
| `free_none` | búsqueda libre sin resultados |

Además, `year_filter_dropped` es una bandera independiente del criterio: indica que el año se descartó para obtener resultados.

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
6. Limpiar carpeta (conserva `.mp4`/`.mkv`, `.srt`, carpetas `subtitle/subtitles`)
7. Guardar como `video.es.srt`

---

## Mover a biblioteca

`move_folder_view` (POST) mueve la carpeta entera desde `MOVE_SOURCE_PATH` hacia `MOVE_DEST_PATH`.

- **Guard**: solo permite la operación si `get_media_root()` normalizado == `MOVE_SOURCE_PATH` normalizado.
- **Botón**: `folder_card.html` lo muestra solo si `can_move` es `True`. Apunta a `#folder-list-container` con `hx-target` + `hx-swap="innerHTML"`.
- **Éxito con carpetas restantes**: se renderiza `folder_list.html` completo con la lista actualizada. Los contadores de las pestañas "Sin subtítulo"/"Con subtítulo" se recalculan solos al re-ejecutarse el `<script>` inline del parcial.
- **Éxito sin carpetas restantes**: respuesta `204` con header `HX-Redirect: /` → el navegador redirige al inicio (evita quedar en una vista vacía).
- **Error**: se renderiza `folder_list.html` con `move_error` seteado, que muestra un banner rojo arriba de las pestañas.

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
INSTALLED_APPS = ["django.contrib.staticfiles", "browser"]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "browser.middleware.MediaRootOverrideMiddleware",
]
DATABASES = {}   # sin base de datos
STATICFILES_DIRS = [BASE_DIR / "browser" / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
STATIC_URL = "/static/"
VIDEO_EXTENSIONS = [".mp4", ".mkv"]
```

Notas:
- No se incluye `django.contrib.sessions` ni `SessionMiddleware` — la biblioteca activa va por cookie firmada, no por sesiones.
- `MediaRootOverrideMiddleware` va **después** de `SessionMiddleware` si algún día se agrega (hoy no aplica).

---

## Archivos estáticos PWA (opcionales, no requeridos para ícono)
Los siguientes archivos existen en `browser/static/browser/` pero no se referencian desde el código — pueden eliminarse sin impacto:
- `sw.js`, `registerSW.js`, `manifest.webmanifest`, `icon-192.png`, `icon-512.png`

---

## Cambios recientes

### Reintento sin año en búsqueda de subtítulos
- `views.py`: si `search_subtitles(title, year)` devuelve vacío y la carpeta tiene año, reintenta con `year=""`. Aplica en búsqueda automática y en "Ver todos". Bandera `year_filter_dropped` en contexto.
- `results.html`: badge ámbar `.criteria-badge-warn` al lado del criterio cuando `year_filter_dropped`. La búsqueda libre se muestra también en `criteria == "none"`.

### Refresco de lista al mover carpeta
- `move_folder_view`: en éxito devuelve el parcial completo `folder_list.html` (o `HX-Redirect: /` si no quedan carpetas). En error, el parcial con `move_error`.
- `folder_card.html`: el botón "mover" apunta a `#folder-list-container` con `hx-swap="innerHTML"`.
- `folder_list.html`: los contadores se recalculan solos al re-ejecutarse el `<script>` inline (no depende de un listener `htmx:afterSwap`).

### Switch de biblioteca
- `browser/middleware.py` (nuevo): `MediaRootOverrideMiddleware` + `set_media_root_cookie` + `get_current_media_root_override`.
- `config.get_media_root()`: prioridad cookie > config.json > settings.
- `switch_media_root_view` (nuevo POST): valida contra `media_root_options` y setea cookie firmada.
- `index.html`: segmented control (2 opciones) o flechas prev/next (3+), con nombre corto del path.

### config.json fuera del repo
- `.gitignore`: `config.json` ignorado.
- `config.json.sample`: plantilla nueva.
- `.env.sample`: plantilla nueva con todas las variables.

---

## Bugs corregidos en sesiones anteriores
- `filesystem.py`: `_RESOLUTION_PATTERN` y `_TYPE_PATTERN` usaban comillas simples en raw strings haciendo que `\b` se interpretara como backspace (`\x08`). Los patrones nunca matcheaban — resolución y tipo siempre caían al default.
- `views.py` (`download_and_save`): `rename_plain_srt_to_english` y `clean_folder` se llamaban dos veces consecutivas.
- `settings.html`: `onclick="addWord()"` → `addChip('word')` tras unificar el script JS.
- `settings.html`: comillas en `onclick="removeChip()"` mal escapadas generaban `removeChip(,0)`.
- `settings.html`: separador `\n` en atributos `value=""` normalizado a espacio por el browser (HTML5). Cambiado a coma para `preferred_words`; JSON para `release_types` y `resolutions`.

---

## Pendientes / mejoras posibles
- Caché de resultados SubX API por título+año (evitar ~2s en cada entrada a carpeta)
- Botón "Actualizar biblioteca" para invalidar caché manualmente
- Indicador visual de subtítulo `.en.srt` en la lista de carpetas
- Aplicar el reintento sin año también en `search_with_fallback` (rama keyword)
- Extender la captura manual de cookie de Cloudflare a otros proveedores (hoy solo subx-bridge)

### Completados
- ~~Soporte para más extensiones de video (.mkv, .avi)~~ → `.mkv` soportado; `.avi` no
- ~~Refresco de contadores al mover carpeta~~ → resuelto con re-render del parcial
- ~~Switch de biblioteca desde el index~~ → resuelto con cookie firmada