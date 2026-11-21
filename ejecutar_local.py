"""Arranca TODO en un solo computador (para desarrollo y demos): NATS, coordinador, los 5 nodos y el dashboard.

  python ejecutar_local.py                 # abre http://localhost:8000
  python ejecutar_local.py --ticks 300 --sin-dashboard --intervalo 0
  python ejecutar_local.py --solo tunja,colombia   # solo algunos nodos (los demás en otros PCs)

Ctrl+C detiene todo.
"""
import argparse
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
NODOS = ["internacional", "colombia", "capitales", "departamentos", "tunja"]


def binario_nats():
    ruta = shutil.which("nats-server")
    if ruta:
        return ruta
    # paquete pip nats-server-bin: deja el binario junto al python del venv (no trae módulo importable)
    for d in (Path(sys.executable).parent, Path(sys.executable).parent / "Scripts"):
        for nombre in ("nats-server", "nats-server.exe"):
            if (d / nombre).exists():
                return str(d / nombre)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticks", type=int, default=0)
    ap.add_argument("--intervalo", type=float)
    ap.add_argument("--sin-dashboard", action="store_true")
    ap.add_argument("--sin-nats", action="store_true", help="usar un NATS que ya está corriendo")
    ap.add_argument("--solo", help="lista de nodos a lanzar aquí, separados por coma")
    ap.add_argument("--procesos", type=int, default=1)
    ap.add_argument("--puerto", type=int, default=8000)
    a = ap.parse_args()

    env = dict(os.environ)
    env.setdefault("NATS_URL", "nats://127.0.0.1:4222")
    env["PYTHONUNBUFFERED"] = "1"
    procs = []

    def lanzar(nombre, args):
        print(f"> {nombre}: {' '.join(args)}")
        p = subprocess.Popen(args, cwd=RAIZ, env=env)
        procs.append((nombre, p))
        return p

    if not a.sin_nats:
        nats_bin = binario_nats()
        if not nats_bin:
            sys.exit("No encontré nats-server. Instala con: pip install nats-server-bin  (o descárgalo de nats.io)")
        args = [nats_bin, "-p", "4222", "-m", "8222"]
        if env.get("NATS_TOKEN"):
            args += ["--auth", env["NATS_TOKEN"]]
        lanzar("nats", args)
        time.sleep(1.0)

    coord = [sys.executable, "-m", "sim.coordinador"]
    if a.ticks:
        coord += ["--ticks", str(a.ticks)]
    if a.intervalo is not None:
        coord += ["--intervalo", str(a.intervalo)]
    coordinador = lanzar("coordinador", coord)
    if not a.sin_dashboard:
        lanzar("dashboard", [sys.executable, "-m", "dashboard.servidor", "--puerto", str(a.puerto)])
    for n in (a.solo.split(",") if a.solo else NODOS):
        lanzar(n, [sys.executable, "-m", "sim.nodo", "--nodo", n.strip(), "--procesos", str(a.procesos)])
    if not a.sin_dashboard:
        print(f"\nDashboard: http://localhost:{a.puerto}\n")

    esenciales = [p for n, p in procs if n in ("nats", "coordinador")]
    avisados = set()
    try:
        # Si un nodo se cae, la simulación sigue (tolerancia a fallos); solo paramos si cae NATS o el reloj.
        while all(p.poll() is None for p in esenciales):
            for nombre, p in procs:
                if p.poll() is not None and nombre not in avisados:
                    avisados.add(nombre)
                    print(f"! {nombre} terminó (código {p.returncode}); el resto sigue corriendo")
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        for nombre, p in reversed(procs):
            if p.poll() is None:
                if os.name == "nt":
                    p.terminate()
                else:
                    p.send_signal(signal.SIGINT)
        for _, p in procs:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()


if __name__ == "__main__":
    main()
