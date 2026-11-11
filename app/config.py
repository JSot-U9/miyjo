"""Configuración central. Todo se puede sobreescribir con variables de entorno."""
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("MIYJO_DATA_DIR", BASE_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'miyjo.db'}")

# Modo demostración: muestra el código OTP en pantalla, habilita /demo y carga familias de ejemplo.
# En el piloto con familias reales: MIYJO_DEMO=0 y conectar un proveedor real de WhatsApp/SMS.
DEMO = os.getenv("MIYJO_DEMO", "1") == "1"

COMISION = float(os.getenv("MIYJO_COMISION", "0.12"))  # 12 % por reserva (supuesto editable)
SOPORTE_WHATSAPP = os.getenv("MIYJO_SOPORTE_WHATSAPP", "51900000000")  # número de ayuda (sin +)

# Lima no usa horario de verano: UTC-5 fijo, sin dependencias de tzdata.
LIMA = timezone(timedelta(hours=-5))


def now() -> datetime:
    """Hora local de Lima (naive). Toda la base de datos guarda esta hora."""
    return datetime.now(LIMA).replace(tzinfo=None, microsecond=0)


def _secret() -> str:
    env = os.getenv("MIYJO_SECRET")
    if env:
        return env
    f = DATA_DIR / "secret.key"
    if not f.exists():
        f.write_text(secrets.token_hex(32))
    return f.read_text().strip()


SECRET_KEY = _secret()
