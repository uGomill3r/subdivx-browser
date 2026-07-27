#!/usr/bin/env python3
"""
Renueva las cookies de Cloudflare (cf_clearance, sdx) necesarias para subx-bridge.

Uso típico: disparado por cron cada pocas horas. Abre un Chromium headless
UNA sola vez (no queda residente), resuelve el challenge de Cloudflare visitando
subdivx.com, extrae las cookies, actualiza el .env de subx-bridge y reinicia
el contenedor con `docker compose restart`.

Requiere:
    pip install playwright python-dotenv --break-system-packages
    playwright install chromium

Ejemplo de cron (cada 4 horas):
    0 */4 * * * /usr/bin/python3 /home/pi/renew_subx_bridge_cookie.py >> /home/pi/renew_subx_bridge_cookie.log 2>&1
"""

import argparse
import logging
import subprocess
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s renew_subx_bridge_cookie — %(message)s",
)
logger = logging.getLogger(__name__)

SUBDIVX_URL = "https://www.subdivx.com"
DEFAULT_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64; rv:148.0) Gecko/20100101 Firefox/148.0"
COOKIE_WAIT_TIMEOUT_MS = 30_000  # 30s para que Cloudflare emita cf_clearance


def fetch_cookies(user_agent: str, timeout_ms: int, headless: bool, debug_dir: Path | None) -> dict:
    """
    Abre un Chromium y visita Subdivx esperando a que Cloudflare emita cf_clearance.
    Retorna un dict con cf_clearance y sdx.
    Lanza RuntimeError si no se pudo conseguir cf_clearance dentro del timeout.

    Si debug_dir se especifica, guarda un screenshot y el HTML de la página en caso
    de fallo, para poder inspeccionar qué mostró Cloudflare (bloqueo simple vs.
    challenge interactivo vs. detección de automatización).
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            # Reduce (no elimina) señales típicas de detección de automatización.
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(user_agent=user_agent)
        # navigator.webdriver es una de las señales más comunes que usa Cloudflare
        # para detectar navegadores automatizados; la enmascaramos antes de navegar.
        context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )
        page = context.new_page()

        logger.debug("Navegando a %s", SUBDIVX_URL)
        page.goto(SUBDIVX_URL, wait_until="domcontentloaded", timeout=timeout_ms)

        # Cloudflare tarda unos segundos en resolver el challenge JS y setear la cookie.
        cf_clearance = None
        sdx = None
        page.wait_for_timeout(5_000)  # margen inicial para que corra el challenge

        elapsed = 0
        poll_interval_ms = 2_000
        while elapsed < timeout_ms:
            cookies = context.cookies(SUBDIVX_URL)
            cf_clearance = next((c["value"] for c in cookies if c["name"] == "cf_clearance"), None)
            sdx = next((c["value"] for c in cookies if c["name"] == "sdx"), None)
            if cf_clearance:
                break
            page.wait_for_timeout(poll_interval_ms)
            elapsed += poll_interval_ms

        if not cf_clearance and debug_dir is not None:
            debug_dir.mkdir(parents=True, exist_ok=True)
            screenshot_path = debug_dir / "cloudflare_debug.png"
            html_path = debug_dir / "cloudflare_debug.html"
            try:
                page.screenshot(path=str(screenshot_path), full_page=True)
                html_path.write_text(page.content(), encoding="utf-8")
                logger.warning(
                    "No se obtuvo cf_clearance — guardado screenshot en %s y HTML en %s para diagnóstico",
                    screenshot_path, html_path,
                )
            except Exception as e:
                logger.error("No se pudo guardar el material de diagnóstico: %s", e)

        browser.close()

        if not cf_clearance:
            raise RuntimeError(
                "No se obtuvo cf_clearance dentro del timeout — revisá el screenshot/HTML "
                "de diagnóstico (--debug-dir) para confirmar si Cloudflare mostró un challenge "
                "interactivo, un bloqueo directo, o detectó el navegador como automatizado."
            )

        logger.info(
            "Cookies obtenidas — cf_clearance: %d chars, sdx: %s",
            len(cf_clearance), "presente" if sdx else "ausente",
        )
        return {"cf_clearance": cf_clearance, "sdx": sdx or ""}


def update_env_file(env_path: Path, values: dict) -> None:
    """
    Actualiza (o agrega) las claves indicadas en el archivo .env, preservando
    el resto de las líneas tal cual estaban.
    """
    if not env_path.exists():
        raise FileNotFoundError(f"No se encontró el archivo .env en {env_path}")

    lines = env_path.read_text(encoding="utf-8").splitlines()
    keys_pending = set(values.keys())
    new_lines = []

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            new_lines.append(line)
            continue

        key = stripped.split("=", 1)[0].strip()
        if key in values:
            new_lines.append(f"{key}={values[key]}")
            keys_pending.discard(key)
        else:
            new_lines.append(line)

    # Claves que no existían en el archivo se agregan al final.
    for key in keys_pending:
        new_lines.append(f"{key}={values[key]}")

    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    logger.info("Archivo .env actualizado: %s (%d claves)", env_path, len(values))


def restart_bridge(bridge_dir: Path) -> None:
    """Reinicia el contenedor de subx-bridge para que tome las cookies nuevas."""
    try:
        result = subprocess.run(
            ["docker", "compose", "restart"],
            cwd=bridge_dir,
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        )
        logger.info("Contenedor de subx-bridge reiniciado — %s", result.stdout.strip() or "OK")
    except subprocess.CalledProcessError as e:
        logger.error("Fallo al reiniciar el contenedor: %s", e.stderr.strip())
        raise
    except subprocess.TimeoutExpired:
        logger.error("Timeout al reiniciar el contenedor de subx-bridge")
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="Renovar cookies de Cloudflare para subx-bridge")
    parser.add_argument("--bridge-dir", type=Path, default=Path.home() / "subx-bridge",
                         help="Directorio del repo de subx-bridge (donde está el .env y docker-compose.yml)")
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT,
                         help="User-Agent a usar (debe coincidir con SUBDIVX_USER_AGENT del .env)")
    parser.add_argument("--timeout", type=int, default=COOKIE_WAIT_TIMEOUT_MS,
                         help="Timeout en milisegundos para esperar cf_clearance")
    parser.add_argument("--no-restart", action="store_true",
                         help="Solo actualizar el .env, sin reiniciar el contenedor")
    parser.add_argument("--headed", action="store_true",
                         help="Correr con navegador visible (debug local, no usar en cron)")
    parser.add_argument("--debug-dir", type=Path, default=None,
                         help="Si se especifica, guarda screenshot + HTML ahí cuando falla la obtención de cf_clearance")
    args = parser.parse_args()

    env_path = args.bridge_dir / ".env"

    try:
        cookies = fetch_cookies(
            user_agent=args.user_agent,
            timeout_ms=args.timeout,
            headless=not args.headed,
            debug_dir=args.debug_dir,
        )
    except RuntimeError as e:
        logger.error("No se pudo renovar la cookie: %s", e)
        return 1
    except Exception as e:
        logger.error("Error inesperado abriendo el navegador: %s", e)
        return 1

    try:
        update_env_file(env_path, {
            "SUBDIVX_CF_CLEARANCE": cookies["cf_clearance"],
            "SUBDIVX_SDX": cookies["sdx"],
            "SUBDIVX_USER_AGENT": args.user_agent,
        })
    except FileNotFoundError as e:
        logger.error(str(e))
        return 1

    if args.no_restart:
        logger.warning("Contenedor NO reiniciado (--no-restart) — las cookies nuevas no están activas todavía")
        return 0

    try:
        restart_bridge(args.bridge_dir)
    except Exception:
        return 1

    logger.info("Renovación de cookies completada con éxito")
    return 0


if __name__ == "__main__":
    sys.exit(main())