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


def sin_quickedit():
    """Windows: desactiva el "modo de edición rápida" de la consola.

    Con ese modo activo, un clic dentro de la ventana negra selecciona texto y PAUSA el proceso en cuanto
    intenta escribir un log: la simulación o el dashboard parecen congelados hasta presionar Esc/Enter.
    """
    if os.name != "nt":
        return
    try:
        import ctypes
        k32 = ctypes.windll.kernel32
        h = k32.GetStdHandle(-10)  # STD_INPUT_HANDLE
        modo = ctypes.c_uint32()
        if k32.GetConsoleMode(h, ctypes.byref(modo)):
            # quitar ENABLE_QUICK_EDIT_MODE (0x40) y dejar ENABLE_EXTENDED_FLAGS (0x80)
            k32.SetConsoleMode(h, (modo.value & ~0x40) | 0x80)
    except Exception:
        pass


def prioridad_baja():
    """Windows: baja la prioridad del proceso (y de sus subprocesos) a "por debajo de lo normal".

    Si el PC se satura, Windows atiende primero al navegador y al dashboard, así los gráficos no se
    traban; la simulación solo tarda unos milisegundos más en ese tick.
    """
    if os.name != "nt":
        return
    try:
        import ctypes
        k32 = ctypes.windll.kernel32
        k32.SetPriorityClass(k32.GetCurrentProcess(), 0x00004000)  # BELOW_NORMAL_PRIORITY_CLASS
    except Exception:
        pass
