import base64
import logging
import queue
import threading
import time
from pathlib import Path

from django.conf import settings
from playwright.sync_api import sync_playwright

from browser.services.subx_bridge_admin import update_env_file, restart_bridge

logger = logging.getLogger(__name__)

SUBDIVX_URL = "https://www.subdivx.com"

# Viewport fijo: el frontend escala los clicks recibidos sobre la imagen
# (que puede mostrarse en cualquier tamaño) a estas coordenadas reales.
VIEWPORT = {"width": 1280, "height": 800}

SCREENSHOT_INTERVAL_S = 0.4     # cada cuánto se refresca el screenshot
QUEUE_POLL_TIMEOUT_S = 0.1      # cada cuánto se revisa si llegó un click
SAFETY_TIMEOUT_S = 120          # cierre forzado si nadie interactúa a tiempo
NAV_TIMEOUT_MS = 30_000

STATUS_IDLE = "idle"
STATUS_STARTING = "starting"
STATUS_WAITING_CLICK = "waiting_click"
STATUS_SUCCESS = "success"
STATUS_ERROR = "error"
STATUS_TIMEOUT = "timeout"

# Estados en los que el frontend debe seguir haciendo polling.
ACTIVE_STATUSES = (STATUS_STARTING, STATUS_WAITING_CLICK)


class _CookieCaptureState:
    """
    Estado en memoria del proceso para la captura manual de la cookie de
    Cloudflare (screenshot-polling). Es un singleton a nivel de proceso:
    válido porque Django corre con --workers 1 (un solo worker de gunicorn).

    Un único hilo en background maneja el ciclo de vida completo de Playwright
    (goto, screenshots, clicks, detección de cookies). Todas las llamadas a la
    API sync de Playwright deben hacerse desde ESE mismo hilo, por eso los
    clicks que llegan desde las vistas de Django se encolan en `_click_queue`
    en vez de ejecutarse directamente.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._click_queue: "queue.Queue[tuple[float, float]]" = queue.Queue()
        self._stop_event = threading.Event()

        self.status = STATUS_IDLE
        self.screenshot_b64: str | None = None
        self.message = ""
        self.viewport = VIEWPORT

    # ── API pública (llamada desde las vistas Django) ──────────────────────

    def is_active(self) -> bool:
        with self._lock:
            return self.status in ACTIVE_STATUSES

    def start(self) -> None:
        with self._lock:
            if self.status in ACTIVE_STATUSES:
                logger.info("Captura de cookie ya en curso — se ignora nuevo start")
                return

        bridge_dir = Path(getattr(settings, "SUBX_BRIDGE_DIR", "") or "")
        env_path = bridge_dir / ".env"
        if not bridge_dir or not env_path.exists():
            logger.error("No se puede iniciar la captura: no existe %s (revisá SUBX_BRIDGE_DIR)", env_path)
            self._set(
                status=STATUS_ERROR,
                message=f"No se encontró {env_path} — revisá la variable SUBX_BRIDGE_DIR.",
                screenshot_b64=None,
            )
            return

        with self._lock:
            self.status = STATUS_STARTING
            self.screenshot_b64 = None
            self.message = "Iniciando navegador…"
            self._stop_event.clear()
            # Descartar clicks que hayan quedado de una sesión anterior.
            while not self._click_queue.empty():
                try:
                    self._click_queue.get_nowait()
                except queue.Empty:
                    break

        self._thread = threading.Thread(target=self._run, args=(bridge_dir, env_path), daemon=True)
        self._thread.start()
        logger.info("Hilo de captura de cookie de Cloudflare iniciado")

    def request_click(self, x: float, y: float) -> bool:
        """Encola una coordenada de click en píxeles del viewport real."""
        if not self.is_active():
            logger.warning("Click ignorado — no hay captura de cookie activa")
            return False
        self._click_queue.put((x, y))
        return True

    def cancel(self) -> None:
        if self.is_active():
            logger.info("Cancelación de captura de cookie solicitada por el usuario")
        self._stop_event.set()

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "status": self.status,
                "message": self.message,
                "screenshot_b64": self.screenshot_b64,
                "viewport": self.viewport,
            }

    # ── Internos ─────────────────────────────────────────────────────────

    def _set(self, **kwargs) -> None:
        with self._lock:
            for key, value in kwargs.items():
                setattr(self, key, value)

    def _run(self, bridge_dir: Path, env_path: Path) -> None:
        user_agent = getattr(settings, "SUBX_BRIDGE_CF_USER_AGENT", "")

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=["--disable-blink-features=AutomationControlled"],
                )
                context = browser.new_context(user_agent=user_agent, viewport=VIEWPORT)
                # navigator.webdriver es una de las señales más comunes que usa
                # Cloudflare para detectar navegadores automatizados.
                context.add_init_script(
                    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
                )
                page = context.new_page()

                logger.debug("Navegando a %s para captura manual de cookie", SUBDIVX_URL)
                page.goto(SUBDIVX_URL, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)

                self._set(
                    status=STATUS_WAITING_CLICK,
                    message="Esperá a que cargue el challenge y hacé click en el checkbox de verificación.",
                )

                start_time = time.time()
                last_screenshot_time = 0.0

                while True:
                    if self._stop_event.is_set():
                        self._set(status=STATUS_IDLE, message="Captura cancelada.", screenshot_b64=None)
                        logger.info("Captura de cookie cancelada por el usuario")
                        break

                    if time.time() - start_time > SAFETY_TIMEOUT_S:
                        self._set(
                            status=STATUS_TIMEOUT,
                            message="Se agotó el tiempo de espera (2 minutos) sin resolver el challenge.",
                        )
                        logger.warning("Timeout de seguridad alcanzado en captura manual de cookie")
                        break

                    # Reenviar un click pendiente, si llegó alguno desde el frontend.
                    try:
                        x, y = self._click_queue.get(timeout=QUEUE_POLL_TIMEOUT_S)
                        page.mouse.click(x, y)
                        logger.info("Click reenviado a Playwright en (%.0f, %.0f)", x, y)
                    except queue.Empty:
                        pass

                    cookies = context.cookies(SUBDIVX_URL)
                    cf_clearance = next((c["value"] for c in cookies if c["name"] == "cf_clearance"), None)
                    sdx = next((c["value"] for c in cookies if c["name"] == "sdx"), None)

                    if cf_clearance:
                        logger.info("cf_clearance obtenida vía click manual — %d chars", len(cf_clearance))
                        self._set(status=STATUS_STARTING, message="Cookie obtenida — actualizando subx-bridge…")
                        try:
                            update_env_file(env_path, {
                                "SUBDIVX_CF_CLEARANCE": cf_clearance,
                                "SUBDIVX_SDX": sdx or "",
                                "SUBDIVX_USER_AGENT": user_agent,
                            })
                            restart_bridge(bridge_dir)
                            self._set(
                                status=STATUS_SUCCESS,
                                message="Cookie renovada y subx-bridge reiniciado correctamente.",
                            )
                            logger.info("Renovación manual de cookie completada con éxito")
                        except Exception as e:
                            self._set(status=STATUS_ERROR, message=f"Cookie obtenida pero falló la actualización: {e}")
                            logger.error("Error al actualizar .env / reiniciar subx-bridge: %s", e)
                        break

                    now = time.time()
                    if now - last_screenshot_time >= SCREENSHOT_INTERVAL_S:
                        try:
                            png_bytes = page.screenshot()
                            self._set(screenshot_b64=base64.b64encode(png_bytes).decode())
                        except Exception as e:
                            logger.error("Error al capturar screenshot: %s", e)
                        last_screenshot_time = now

                browser.close()
        except Exception as e:
            logger.error("Error inesperado en el hilo de captura de cookie: %s", e)
            self._set(status=STATUS_ERROR, message=f"Error inesperado: {e}", screenshot_b64=None)


# Instancia única a nivel de módulo — actúa como singleton del proceso.
capture_state = _CookieCaptureState()
