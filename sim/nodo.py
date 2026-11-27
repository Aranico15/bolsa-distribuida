"""Servicio de un nodo del mercado. Cada computador corre uno (o varios) de estos.

  python -m sim.nodo --nodo tunja --nats nats://IP_DEL_PRINCIPAL:4222

El nodo espera el tick del reloj global, procesa su economía (con el núcleo paralelo), envía órdenes
a los mercados de otros nodos, responde con las ejecuciones de las órdenes que recibió y publica su
estado. Si el nodo se cae y vuelve, puede reanudar desde su último snapshot (--reanudar).
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import pickle
import time
from pathlib import Path

from . import config
from .bus import Bus
from .economia import Economia
from .macro import BancoCentral, MercadoMundial

log = logging.getLogger("nodo")


class ServicioNodo:
    def __init__(self, nodo_id, url, token, trabajadores=1, dir_estado="estado", reanudar=False):
        self.escenario, self.semilla = config.cargar()
        if nodo_id not in self.escenario["nodos"]:
            raise SystemExit(f"Nodo desconocido: {nodo_id}. Opciones: {', '.join(self.escenario['nodos'])}")
        self.id = nodo_id
        self.cfg = self.escenario["nodos"][nodo_id]
        self.bus = Bus(url, f"nodo-{nodo_id}", token)
        self.dir_estado = Path(dir_estado)
        self.dir_estado.mkdir(parents=True, exist_ok=True)
        self.archivo = self.dir_estado / f"{nodo_id}.pkl"
        sim = self.escenario["simulacion"]
        self.snapshot_cada = sim["snapshot_cada"]
        self.ultimo_snapshot = 0.0
        self.banco = self.mundo = None
        if reanudar and self.archivo.exists():
            with self.archivo.open("rb") as fh:
                guardado = pickle.load(fh)
            self.eco, self.banco, self.mundo = guardado["eco"], guardado["banco"], guardado["mundo"]
            from .kernel import Paralelo
            self.eco.paralelo = Paralelo(trabajadores)
            log.info("Reanudado desde snapshot en t=%s", self.eco.t)
        else:
            self.eco = Economia(nodo_id, self.escenario, self.semilla, trabajadores, sim["semilla_aleatoria"])
            if self.cfg.get("banco_central"):
                self.banco = BancoCentral(self.semilla, sim["nodos_colombia"])
            if self.cfg.get("mercado_mundial"):
                self.mundo = MercadoMundial(self.escenario, self.semilla, sim["semilla_aleatoria"])
        self.ordenes_in, self.fills_in = [], []
        self.catalogos: dict[str, dict] = {}
        self.bajas_remotas: set[str] = set()
        self.politica = {"tasa": self.semilla["paises"]["COL"]["tasa_politica"]}
        self.ultimo_mundo = {"trm": self.semilla["trm"]["ultimo"], "demanda_externa": 1.0, "petroleo_rel": 1.0}
        self.choques_activos: list[dict] = []
        self.tick_pendiente = None
        self.ocupado = False
        self.flujo_prev = 0.0

    async def iniciar(self):
        await self.bus.conectar()
        await self.bus.sub("sim.tick", self.on_tick)
        await self.bus.sub(f"ordenes.{self.id}", self.on_ordenes)
        await self.bus.sub(f"fills.{self.id}", self.on_fills)
        await self.bus.sub("estado.*", self.on_estado)
        await self.bus.sub("politica.colombia", self.on_politica)
        await self.bus.sub("mundo", self.on_mundo)
        await self.bus.sub("sim.quien", self.on_quien)
        await self.bus.flush()
        await self.anunciar()
        log.info("Nodo %s listo (%d agentes, %d empresas, %d procesos)", self.id, len(self.eco.tipo),
                 sum(e.viva for e in self.eco.empresas), self.eco.paralelo.trabajadores)

    async def anunciar(self):
        await self.bus.pub(f"sim.hola.{self.id}", {"nodo": self.id, "t": self.eco.t,
                                                   "agentes": int(len(self.eco.tipo))})

    async def on_quien(self, _, __):
        await self.anunciar()

    async def on_ordenes(self, _, datos):
        self.ordenes_in.extend(datos)

    async def on_fills(self, _, datos):
        self.fills_in.extend(datos)

    async def on_estado(self, asunto, datos):
        if datos["nodo"] == self.id:
            return
        self.catalogos[datos["nodo"]] = datos["activos"]
        self.bajas_remotas.update(datos.get("bajas", []))
        if self.banco:
            self.banco.recibir(datos)

    async def on_politica(self, _, datos):
        self.politica = datos

    async def on_mundo(self, _, datos):
        if not self.mundo:
            self.ultimo_mundo = datos

    async def on_tick(self, _, datos):
        self.tick_pendiente = datos
        if self.ocupado:
            return  # se procesará el más reciente al terminar el actual
        self.ocupado = True
        try:
            while self.tick_pendiente is not None:
                tick, self.tick_pendiente = self.tick_pendiente, None
                await self.procesar(tick)
        finally:
            self.ocupado = False

    async def procesar(self, tick):
        t0 = time.perf_counter()
        t = tick["t"]
        choques = tick.get("choques", [])
        # Choques con duración: se mantienen activos varios ticks.
        for c in choques:
            self.choques_activos.append({**c, "hasta": t + int(c.get("duracion", 60))})
        self.choques_activos = [c for c in self.choques_activos if c["hasta"] > t]

        if self.mundo:
            self.ultimo_mundo = self.mundo.paso(t, choques, self.flujo_prev, self.politica.get("tasa"))
            self.ultimo_mundo["fecha"] = tick.get("fecha")
            await self.bus.pub("mundo", self.ultimo_mundo)
        if self.banco:
            self.politica = self.banco.paso(t, choques)
            self.politica["fecha"] = tick.get("fecha")
            await self.bus.pub("politica.colombia", self.politica)

        macro = dict(self.ultimo_mundo)
        macro["tasa"] = self.politica.get("tasa")
        ordenes, self.ordenes_in = self.ordenes_in, []
        fills, self.fills_in = self.fills_in, []
        catalogo = {}
        for activos in self.catalogos.values():
            catalogo.update(activos)
        if self.bajas_remotas:
            self.eco.aplicar_bajas(self.bajas_remotas)
            for tk in self.bajas_remotas:
                catalogo.pop(tk, None)
        res = await asyncio.to_thread(self.eco.paso, t, macro, ordenes, fills, catalogo, self.choques_activos)
        self.flujo_prev = self.eco.flujo_usd

        for destino, lote in res["ordenes"].items():
            await self.bus.pub(f"ordenes.{destino}", lote)
        for origen, lote in res["fills"].items():
            await self.bus.pub(f"fills.{origen}", lote)
        ms = (time.perf_counter() - t0) * 1000
        estado = res["estado"]
        estado["ms"] = round(ms, 2)
        estado["fecha"] = tick.get("fecha")
        estado["remotas_enviadas"] = sum(len(v) for v in res["ordenes"].values())
        estado["remotas_recibidas"] = len(ordenes)
        estado["flujos"] = {destino: len(lote) for destino, lote in res["ordenes"].items()}
        await self.bus.pub(f"estado.{self.id}", estado)
        if res["eventos"]:
            await self.bus.pub(f"eventos.{self.id}", res["eventos"])
        await self.bus.pub(f"sim.ack.{self.id}", {"t": t, "nodo": self.id, "ms": round(ms, 2),
                                                  "enviado": tick.get("enviado"), "agentes": int(len(self.eco.tipo)),
                                                  "bytes": self.bus.bytes_enviados})
        # Snapshot cada `snapshot_cada` ticks, pero no más de uno cada 15 s: a velocidad máxima se
        # escribían ~0,7 MB por nodo cada 2 s (y OneDrive/Syncthing los resincronizaban sin parar).
        if t % self.snapshot_cada == 0 and time.monotonic() - self.ultimo_snapshot >= 15:
            self.ultimo_snapshot = time.monotonic()
            await asyncio.to_thread(self.guardar)

    def guardar(self):
        tmp = self.archivo.with_suffix(".tmp")
        try:
            with tmp.open("wb") as fh:
                pickle.dump({"eco": self.eco, "banco": self.banco, "mundo": self.mundo}, fh)
            for intento in range(3):  # en Windows, OneDrive/antivirus a veces bloquea el archivo un instante
                try:
                    tmp.replace(self.archivo)
                    return
                except PermissionError:
                    time.sleep(0.2)
            log.warning("No pude reemplazar %s (archivo bloqueado); se intenta en el próximo snapshot", self.archivo)
        except Exception:
            log.exception("Fallo guardando el snapshot (la simulación sigue)")


def procesos_utiles(pedido, nodo_id):
    """--procesos 0 = "los que sirvan": no más que núcleos ni que bloques de agentes del nodo.

    Antes, en un Ryzen de 16 núcleos cada nodo abría 16 procesos para ~300 agentes (5 bloques de trabajo):
    11 procesos ociosos por nodo comiendo RAM y arranque, sin ganar velocidad.
    """
    if pedido and pedido > 0:
        return pedido
    from .kernel import SUBBLOQUE
    escenario, _ = config.cargar()
    agentes = escenario["nodos"].get(nodo_id, {}).get("agentes", 0)
    return max(1, min(os.cpu_count() or 1, -(-agentes // SUBBLOQUE)))


async def main_async(a):
    s = ServicioNodo(a.nodo, config.nats_url(a.nats), config.nats_token(a.token),
                     procesos_utiles(a.procesos, a.nodo), a.dir_estado, a.reanudar)
    await s.iniciar()
    try:
        await asyncio.Event().wait()
    finally:
        s.eco.paralelo.cerrar()
        await s.bus.cerrar()


def main():
    ap = argparse.ArgumentParser(description="Nodo del mercado distribuido")
    ap.add_argument("--nodo", required=True, help="tunja | capitales | departamentos | colombia | internacional")
    ap.add_argument("--nats", help="URL(s) de NATS separadas por coma (o variable NATS_URL)")
    ap.add_argument("--token", help="token de NATS (o variable NATS_TOKEN)")
    ap.add_argument("--procesos", type=int, default=1, help="procesos para el núcleo paralelo (0 = automático: los útiles según núcleos y agentes)")
    ap.add_argument("--dir-estado", default="estado")
    ap.add_argument("--reanudar", action="store_true", help="continuar desde el último snapshot")
    a = ap.parse_args()
    config.sin_quickedit()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    try:
        asyncio.run(main_async(a))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
