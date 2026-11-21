"""Reloj global y supervisor de la simulación (corre en el PC principal).

Publica un tick, espera la confirmación de cada nodo vivo (barrera con tiempo límite), detecta nodos
caídos y reincorporados, reparte los choques económicos a todos en el mismo tick y guarda todo en
runs/<fecha>/ para la analítica.

  python -m sim.coordinador --nats nats://127.0.0.1:4222
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import logging
import time
from datetime import datetime
from pathlib import Path

import numpy as np

from . import config
from .bus import Bus

log = logging.getLogger("coordinador")


class Registro:
    """Escribe CSVs por corrida: macro, nodos, regiones, precios y eventos."""

    def __init__(self, carpeta: Path):
        carpeta.mkdir(parents=True, exist_ok=True)
        self.carpeta = carpeta
        self.archivos, self.escritores = {}, {}

    def fila(self, nombre, d: dict):
        if nombre not in self.escritores:
            fh = (self.carpeta / f"{nombre}.csv").open("w", newline="", encoding="utf-8")
            w = csv.DictWriter(fh, fieldnames=list(d.keys()), extrasaction="ignore")
            w.writeheader()
            self.archivos[nombre], self.escritores[nombre] = fh, w
        self.escritores[nombre].writerow(d)

    def flush(self):
        for fh in self.archivos.values():
            fh.flush()

    def cerrar(self):
        for fh in self.archivos.values():
            fh.close()


class Coordinador:
    def __init__(self, url, token, intervalo=None, ticks=0, dir_runs="runs"):
        self.escenario, self.semilla = config.cargar()
        sim = self.escenario["simulacion"]
        self.intervalo = sim["segundos_por_tick"] if intervalo is None else intervalo
        self.timeout = sim["timeout_ack_s"]
        self.ticks_caido = sim["ticks_para_caido"]
        self.max_ticks = ticks
        self.fecha0 = np.datetime64(sim["fecha_inicio"])
        self.bus = Bus(url, "coordinador", token)
        self.nodos = {n: {"vivo": False, "fallos": 0, "ultimo_t": -1, "ms": None, "rtt_ms": None, "red_ms": None,
                          "agentes": self.escenario["nodos"][n]["agentes"], "visto": None, "bytes": 0}
                      for n in self.escenario["nodos"]}
        self.t = 0
        self.acks: set[str] = set()
        self.evento_acks = asyncio.Event()
        self.choques_pendientes: list[dict] = []
        self.pausado = False
        self.reg = Registro(Path(dir_runs) / datetime.now().strftime("%Y%m%d-%H%M%S"))
        self.t_inicio = time.time()

    async def iniciar(self):
        await self.bus.conectar()
        await self.bus.sub("sim.ack.*", self.on_ack)
        await self.bus.sub("sim.hola.*", self.on_hola)
        await self.bus.sub("control.>", self.on_control)
        await self.bus.sub("estado.*", self.on_estado)
        await self.bus.sub("mundo", self.on_mundo)
        await self.bus.sub("politica.colombia", self.on_politica)
        await self.bus.sub("eventos.*", self.on_eventos)
        log.info("Coordinador listo. Registro en %s", self.reg.carpeta)

    # ------------------------------------------------------------ mensajes
    async def on_hola(self, _, d):
        n = self.nodos.get(d["nodo"])
        if n is not None:
            if n["visto"] is None:
                log.info("Nodo %s se unió (t local %s, %s agentes)", d["nodo"], d["t"], d["agentes"])
            else:
                log.warning("Nodo %s se reincorporó desde t local %s", d["nodo"], d["t"])
            n["vivo"], n["fallos"], n["agentes"] = True, 0, d["agentes"]

    async def on_ack(self, _, d):
        n = self.nodos.get(d["nodo"])
        if n is None:
            return
        ahora = time.time()
        if not n["vivo"]:
            if n["visto"] is None:
                log.info("Nodo %s se unió", d["nodo"])
            else:
                log.warning("Nodo %s se reincorporó", d["nodo"])
        n.update(vivo=True, fallos=0, ultimo_t=d["t"], ms=d["ms"], agentes=d["agentes"], visto=ahora, bytes=d["bytes"])
        if d.get("enviado"):
            n["rtt_ms"] = round((ahora - d["enviado"]) * 1000, 2)
            n["red_ms"] = round(max(n["rtt_ms"] - d["ms"], 0), 2)  # tiempo de red ≈ ida y vuelta - cómputo
        if d["t"] == self.t:
            self.acks.add(d["nodo"])
            if self.acks >= {k for k, v in self.nodos.items() if v["vivo"]}:
                self.evento_acks.set()

    async def on_control(self, asunto, d):
        if asunto == "control.choque":
            log.warning("Choque recibido: %s", d)
            self.choques_pendientes.append(d)
        elif asunto == "control.pausa":
            self.pausado = bool(d.get("pausa", not self.pausado))
        elif asunto == "control.velocidad":
            self.intervalo = max(0.0, float(d.get("segundos_por_tick", self.intervalo)))

    async def on_estado(self, _, d):
        ind = d["ind"]
        self.reg.fila("nodos", {"t": d["t"], "fecha": d.get("fecha"), "nodo": d["nodo"], "ms": d.get("ms"),
                                "rtt_ms": self.nodos[d["nodo"]]["rtt_ms"], "red_ms": self.nodos[d["nodo"]]["red_ms"],
                                "remotas_enviadas": d.get("remotas_enviadas"), "remotas_recibidas": d.get("remotas_recibidas"),
                                **{k: v for k, v in ind.items() if not isinstance(v, dict)}})
        for cod, r in d["regiones"].items():
            self.reg.fila("regiones", {"t": d["t"], "nodo": d["nodo"], "region": cod, **r})
        for tk, a in d["activos"].items():
            self.reg.fila("precios", {"t": d["t"], "ticker": tk, "nodo": d["nodo"], "region": a["reg"],
                                      "sector": a["sec"], "moneda": a["mon"], "o": a["o"], "h": a["h"], "l": a["l"],
                                      "c": a["c"], "v": a["v"], "cap": a["cap"]})

    async def on_mundo(self, _, d):
        self.reg.fila("mundo", {"t": d["t"], "trm": d["trm"], "petroleo": d["petroleo"],
                                "demanda_externa": d["demanda_externa"], "tasa_col": d["tasa_col"],
                                **{f"tasa_{k}": v for k, v in d["tasas"].items()}})

    async def on_politica(self, _, d):
        self.reg.fila("politica", d)

    async def on_eventos(self, _, lote):
        for e in lote:
            self.reg.fila("eventos", e)

    # ------------------------------------------------------------ reloj
    def fecha(self, t):
        return str(np.busday_offset(self.fecha0, t, roll="forward"))

    async def correr(self):
        log.info("Esperando nodos... (arranca cuando haya al menos uno)")
        while not any(n["vivo"] for n in self.nodos.values()):
            await asyncio.sleep(0.5)
        await asyncio.sleep(1.5)  # deja que los demás se anuncien
        while not self.max_ticks or self.t < self.max_ticks:
            if self.pausado:
                await asyncio.sleep(0.2)
                await self.publicar_global()
                continue
            inicio = time.time()
            self.t += 1
            self.acks = set()
            self.evento_acks.clear()
            choques, self.choques_pendientes = self.choques_pendientes, []
            await self.bus.pub("sim.tick", {"t": self.t, "fecha": self.fecha(self.t), "choques": choques,
                                            "enviado": time.time()})
            for c in choques:
                self.reg.fila("choques", {"t": self.t, **c})
            if choques:
                await self.bus.pub("eventos.coordinador", [
                    {"t": self.t, "nodo": "coordinador", "tipo": "choque", "region": None,
                     "texto": f"Choque {c['tipo'].replace('_', ' ')} ×{c.get('magnitud', 1)} sobre {c.get('objetivo', 'todos')}"}
                    for c in choques])
            try:
                await asyncio.wait_for(self.evento_acks.wait(), timeout=self.timeout)
            except asyncio.TimeoutError:
                pass
            for nombre, n in self.nodos.items():
                if n["vivo"] and nombre not in self.acks:
                    n["fallos"] += 1
                    if n["fallos"] >= self.ticks_caido:
                        n["vivo"] = False
                        log.error("Nodo %s marcado como CAÍDO (sin respuesta en %d ticks); la simulación sigue",
                                  nombre, n["fallos"])
                        await self.bus.pub("eventos.coordinador", [{"t": self.t, "nodo": nombre, "tipo": "nodo_caido",
                                                                    "texto": f"Nodo {nombre} sin respuesta", "region": None}])
            await self.publicar_global(time.time() - inicio)
            if self.t % 20 == 0:
                self.reg.flush()
                vivos = [k for k, v in self.nodos.items() if v["vivo"]]
                log.info("t=%d %s vivos=%s", self.t, self.fecha(self.t), ",".join(vivos))
            espera = self.intervalo - (time.time() - inicio)
            if espera > 0:
                await asyncio.sleep(espera)
        self.reg.cerrar()

    async def publicar_global(self, duracion=None):
        transcurrido = time.time() - self.t_inicio
        await self.bus.pub("sim.global", {
            "t": self.t, "fecha": self.fecha(self.t), "pausado": self.pausado, "intervalo": self.intervalo,
            "ticks_por_s": round(self.t / transcurrido, 3) if transcurrido else 0,
            "duracion_tick_ms": round(duracion * 1000, 1) if duracion else None,
            "nodos": self.nodos, "run": str(self.reg.carpeta),
        })


async def main_async(a):
    c = Coordinador(config.nats_url(a.nats), config.nats_token(a.token), a.intervalo, a.ticks, a.dir_runs)
    await c.iniciar()
    try:
        await c.correr()
    finally:
        c.reg.cerrar()
        await c.bus.cerrar()


def main():
    ap = argparse.ArgumentParser(description="Reloj global de la simulación")
    ap.add_argument("--nats")
    ap.add_argument("--token")
    ap.add_argument("--intervalo", type=float, help="segundos por tick (por defecto el del escenario)")
    ap.add_argument("--ticks", type=int, default=0, help="detener tras N ticks (0 = sin límite)")
    ap.add_argument("--dir-runs", default="runs")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    try:
        asyncio.run(main_async(a))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
