import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def update_env_file(env_path: Path, values: dict) -> None:
    """
    Actualiza (o agrega) las claves indicadas en el archivo .env de subx-bridge,
    preservando el resto de las líneas tal cual estaban.
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
    logger.info("Archivo .env de subx-bridge actualizado: %s (%d claves)", env_path, len(values))


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
        logger.error("Fallo al reiniciar el contenedor de subx-bridge: %s", e.stderr.strip())
        raise
    except subprocess.TimeoutExpired:
        logger.error("Timeout al reiniciar el contenedor de subx-bridge")
        raise
