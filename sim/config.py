import json
import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def cargar():
    escenario = json.loads((RAIZ / "config" / "escenario.json").read_text(encoding="utf-8"))
    semilla = json.loads((RAIZ / "config" / "semilla.json").read_text(encoding="utf-8"))
    return escenario, semilla


def nats_url(arg=None):
    return arg or os.environ.get("NATS_URL", "nats://127.0.0.1:4222")


def nats_token(arg=None):
    return arg or os.environ.get("NATS_TOKEN") or None
