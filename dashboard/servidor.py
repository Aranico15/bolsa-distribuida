"""Dashboard en tiempo real: escucha NATS y empuja los datos al navegador por WebSocket.

  python -m dashboard.servidor --nats nats://127.0.0.1:4222 --puerto 8000
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from sim import config
from sim.bus import Bus

log = logging.getLogger("dashboard")
ESTATICO = Path(__file__).parent / "static"
NODOS_COL = ("tunja", "capitales", "departamentos", "colombia")


class Estado:
    def __init__(self):
        self.glob = {}
        self.nodos = {}                                   # último estado por nodo (sin activos)
        self.activos = {}                                 # ticker -> resumen
        self.velas = defaultdict(lambda: deque(maxlen=400))
        self.series_nodo = defaultdict(lambda: deque(maxlen=600))
        self.series_region = defaultdict(lambda: deque(maxlen=300))
        self.mundo = deque(maxlen=600)
        self.politica = deque(maxlen=600)
        self.eventos = deque(maxlen=250)
        self.pendiente = {"velas": {}, "nodos": set(), "eventos": [], "mundo": [], "politica": []}

    def on_estado(self, d):
        fecha = d.get("fecha") or str(d["t"])
        nodo = d["nodo"]
        for tk, a in d["activos"].items():
            ant = self.velas[tk][-1]["close"] if self.velas[tk] else a["o"]
            vela = {"time": fecha, "t": d["t"], "open": a["o"], "high": a["h"], "low": a["l"], "close": a["c"],
                    "value": a["v"]}
            if self.velas[tk] and self.velas[tk][-1]["time"] == fecha:
                self.velas[tk][-1] = vela
            else:
                self.velas[tk].append(vela)
            primero = self.velas[tk][0]["open"]
            self.activos[tk] = {"tk": tk, "p": a["p"], "var": (a["c"] / ant - 1) if ant else 0.0,
                                "var_total": (a["c"] / primero - 1) if primero else 0.0, "v": a["v"],
                                "nodo": nodo, "reg": a["reg"], "sec": a["sec"], "mon": a["mon"], "cap": a["cap"],
                                "t": d["t"]}
            self.pendiente["velas"][tk] = vela
        for tk in d.get("bajas", []):
            if tk in self.activos:
                self.activos.pop(tk)
        resumen = {k: v for k, v in d.items() if k != "activos"}
        self.nodos[nodo] = resumen
        self.series_nodo[nodo].append({"time": fecha, "t": d["t"], **{k: d["ind"][k] for k in
                                       ("indice", "inflacion", "desempleo", "pib", "tasa", "gini", "empresas")},
                                       "ms": d.get("ms")})
        for cod, r in d["regiones"].items():
            self.series_region[cod].append({"t": d["t"], "time": fecha, "indice": r["indice"],
                                            "inflacion": r["inflacion"], "desempleo": r["desempleo"],
                                            "pib": r["pib"], "empresas": r["empresas"]})
        self.pendiente["nodos"].add(nodo)

    def regiones(self):
        out = {}
        for nodo, est in self.nodos.items():
            for cod, r in est["regiones"].items():
                s = self.series_region[cod]
                base = s[-21]["indice"] if len(s) > 21 else s[0]["indice"] if s else r["indice"]
                out[cod] = {**r, "nodo": nodo, "var20": (r["indice"] / base - 1) if base else 0.0}
        return out

    def colombia(self):
        caps = [a for a in self.activos.values() if a["nodo"] in NODOS_COL]
        ests = [self.nodos[n] for n in NODOS_COL if n in self.nodos]
        if not ests:
            return {}
        pib = sum(e["ind"]["pib"] for e in ests) or 1
        return {
            "indice": sum(e["ind"]["indice"] * e["ind"]["pib"] for e in ests) / pib,
            "inflacion": sum(e["ind"]["inflacion"] * e["ind"]["pib"] for e in ests) / pib,
            "desempleo": sum(e["ind"]["desempleo"] * e["ind"]["pib"] for e in ests) / pib,
            "empresas": len(caps),
            "quiebras": sum(e["ind"]["quiebras"] for e in ests),
            "nuevas": sum(e["ind"]["nuevas"] for e in ests),
        }

    def snapshot(self):
        return {"tipo": "snapshot", "global": self.glob, "nodos": self.nodos, "activos": self.activos,
                "series_nodo": {k: list(v) for k, v in self.series_nodo.items()},
                "series_region": {k: list(v) for k, v in self.series_region.items()},
                "mundo": list(self.mundo), "politica": list(self.politica), "eventos": list(self.eventos),
                "regiones": self.regiones(), "colombia": self.colombia()}

    def delta(self):
        p = self.pendiente
        self.pendiente = {"velas": {}, "nodos": set(), "eventos": [], "mundo": [], "politica": []}
        return {"tipo": "delta", "global": self.glob,
                "nodos": {n: self.nodos[n] for n in p["nodos"]},
                "series_nodo": {n: self.series_nodo[n][-1] for n in p["nodos"]},
                "series_region": {cod: self.series_region[cod][-1] for n in p["nodos"]
                                  for cod in self.nodos[n]["regiones"]},
                "velas": p["velas"], "activos": self.activos, "mundo": p["mundo"], "politica": p["politica"],
                "eventos": p["eventos"], "regiones": self.regiones(), "colombia": self.colombia()}


def crear_app(url, token):
    estado = Estado()
    clientes: set[WebSocket] = set()
    bus = Bus(url, "dashboard", token)

    async def on_estado(_, d):
        estado.on_estado(d)

    async def on_global(_, d):
        estado.glob = d

    async def on_mundo(_, d):
        fila = {"t": d["t"], "time": d.get("fecha") or d["t"], "trm": d["trm"], "petroleo": d["petroleo"], "demanda_externa": d["demanda_externa"],
                "tasas": d["tasas"]}
        estado.mundo.append(fila)
        estado.pendiente["mundo"].append(fila)

    async def on_politica(_, d):
        d["time"] = d.get("fecha") or d["t"]
        estado.politica.append(d)
        estado.pendiente["politica"].append(d)

    async def on_eventos(_, lote):
        estado.eventos.extend(lote)
        estado.pendiente["eventos"].extend(lote)

    async def difundir():
        while True:
            await asyncio.sleep(0.4)
            if not clientes or not (estado.pendiente["nodos"] or estado.pendiente["eventos"]):
                continue
            texto = json.dumps(estado.delta(), separators=(",", ":"))
            for ws in list(clientes):
                try:
                    await ws.send_text(texto)
                except Exception:
                    clientes.discard(ws)

    @asynccontextmanager
    async def vida(app):
        await bus.conectar()
        await bus.sub("estado.*", on_estado)
        await bus.sub("sim.global", on_global)
        await bus.sub("mundo", on_mundo)
        await bus.sub("politica.colombia", on_politica)
        await bus.sub("eventos.*", on_eventos)
        tarea = asyncio.create_task(difundir())
        yield
        tarea.cancel()
        await bus.cerrar()

    app = FastAPI(title="Bolsa distribuida", lifespan=vida)
    app.mount("/static", StaticFiles(directory=ESTATICO), name="static")

    @app.get("/")
    async def inicio():
        return FileResponse(ESTATICO / "index.html")

    @app.get("/nodo/{nodo}")
    async def vista_nodo(nodo: str):
        if nodo not in ("tunja", "capitales", "departamentos", "colombia", "internacional"):
            return FileResponse(ESTATICO / "index.html")
        return FileResponse(ESTATICO / "nodo.html")

    @app.get("/api/velas/{ticker}")
    async def velas(ticker: str):
        return list(estado.velas.get(ticker, []))

    @app.post("/api/choque")
    async def choque(d: dict):
        permitido = {"crisis_financiera", "pandemia", "crisis_internacional", "boom_consumo", "inflacion",
                     "subida_tasas", "bajada_tasas", "boom_petrolero", "guerra_comercial", "fin_guerra_comercial"}
        if d.get("tipo") not in permitido:
            return {"ok": False, "error": "tipo de choque desconocido"}
        c = {"tipo": d["tipo"], "magnitud": float(d.get("magnitud", 1.0)), "objetivo": d.get("objetivo") or "todos",
             "duracion": int(d.get("duracion", 60))}
        await bus.pub("control.choque", c)
        return {"ok": True, "choque": c}

    @app.post("/api/control")
    async def control(d: dict):
        if d.get("accion") == "pausa":
            await bus.pub("control.pausa", {"pausa": bool(d.get("valor", True))})
        elif d.get("accion") == "velocidad":
            await bus.pub("control.velocidad", {"segundos_por_tick": float(d.get("valor", 0.5))})
        return {"ok": True}

    @app.websocket("/ws")
    async def ws(socket: WebSocket):
        await socket.accept()
        await socket.send_text(json.dumps(estado.snapshot(), separators=(",", ":")))
        clientes.add(socket)
        try:
            while True:
                await socket.receive_text()
        except WebSocketDisconnect:
            clientes.discard(socket)

    return app


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nats")
    ap.add_argument("--token")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--puerto", type=int, default=8000)
    a = ap.parse_args()
    config.sin_quickedit()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    uvicorn.run(crear_app(config.nats_url(a.nats), config.nats_token(a.token)), host=a.host, port=a.puerto,
                log_level="warning")


if __name__ == "__main__":
    main()
