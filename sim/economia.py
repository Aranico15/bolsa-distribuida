"""Economía de un nodo: hogares, empresarios, inversionistas, bancos, un formador de liquidez,
empresas que contratan, quiebran y nacen, gobierno por región y un mercado de acciones.

Un tick equivale a un día hábil. Todo el dinero del nodo está en su moneda (COP o USD); los activos
de otros nodos se convierten con la TRM que publica el mercado internacional.
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field

import numpy as np

from .kernel import Paralelo
from .mercado import LibroOrdenes, Orden

HOGAR, EMPRESARIO, INVERSIONISTA, BANCO, CREADOR = range(5)
TIPOS = ["hogar", "empresario", "inversionista", "banco", "creador_mercado"]
DIAS_ANIO, DIAS_MES = 252, 21
SECTORES_EXPORTADORES = {"PET", "MIN", "CAF", "AGR", "FLO", "AZU", "GAN", "PES"}
SECTORES_PETROLEO = {"PET", "MIN"}


@dataclass
class Empresa:
    ticker: str
    region: int
    sector: str
    efectivo: float
    capital: float
    deuda: float
    productividad: float
    acciones: float
    fundador: int
    nacida: int
    viva: bool = True
    perdidas: int = 0
    ingresos: float = 0.0
    utilidad: float = 0.0
    ventas_prom: float = 0.0
    util_mes: deque = field(default_factory=lambda: deque(maxlen=DIAS_MES))
    precios: deque = field(default_factory=lambda: deque(maxlen=21))

    util_ema: float = 0.0

    @property
    def utilidad_anual(self):
        return self.util_ema * DIAS_ANIO

    @property
    def patrimonio(self):
        return self.efectivo + self.capital - self.deuda


class Indice:
    """Índice ponderado por capitalización con divisor (base 1000), como un índice bursátil real."""

    def __init__(self):
        self.divisor = None

    def valor(self, caps_ant: float, caps: float, nuevas_caps: float = 0.0):
        if self.divisor is None:
            self.divisor = max(caps, 1e-9) / 1000.0
        elif nuevas_caps > 0 and caps_ant > 0:
            # una empresa nueva entra sin mover el índice
            self.divisor *= (caps_ant + nuevas_caps) / caps_ant
        return caps / self.divisor if self.divisor else 1000.0


def gini(x):
    x = np.sort(np.clip(x, 0, None))
    if x.sum() <= 0:
        return 0.0
    n = len(x)
    return float((2 * np.arange(1, n + 1) - n - 1).dot(x) / (n * x.sum()))


class Economia:
    def __init__(self, nodo_id: str, escenario: dict, semilla: dict, trabajadores: int = 1, seed: int = 42):
        cfg = escenario["nodos"][nodo_id]
        self.id = nodo_id
        self.cfg = cfg
        self.pais = cfg["pais"]
        self.moneda = cfg["moneda"]
        self.rng = np.random.default_rng(seed + sum(map(ord, nodo_id)))
        self.paralelo = Paralelo(trabajadores)
        self.t = 0
        self.refs = 0
        self.trm0 = semilla["trm"]["ultimo"]
        self.trm = self.trm0
        self.trm_hist = deque([self.trm0] * DIAS_MES, maxlen=DIAS_MES)
        self.eventos = []
        self.totales = {"quiebras": 0, "nuevas": 0, "quiebras_personales": 0, "perdidas_banca": 0.0}

        # --- Regiones y sus reglas (base -> país -> región) ---
        self.regiones = []
        for r in cfg["regiones"]:
            pais_r = r["codigo"] if self.pais == "INT" else self.pais
            datos = semilla["paises"].get(pais_r, semilla["paises"]["COL"])
            reglas = dict(escenario["reglas_base"])
            reglas.update(escenario["reglas_paises"].get(pais_r, {}))
            reglas.update(r.get("reglas", {}))
            reglas["renta_empresas"] = reglas.get("renta_empresas", datos["renta_empresas"])
            if self.moneda == "COP":
                salario = semilla["salario_minimo_col"] * 1.5 * r.get("salario_mult", 1.0)
            else:
                salario = datos["pib_pc_usd"] * 0.45 / 12 * r.get("salario_mult", 1.0)
            pob = semilla["poblacion"].get(r["codigo"], 1_000_000) if self.pais != "INT" else datos["pib_pc_usd"] * 1000
            self.regiones.append({
                "codigo": r["codigo"], "nombre": r["nombre"], "pais": pais_r, "reglas": reglas,
                "sectores": r["sectores"], "salario": salario, "poblacion": pob,
                "pi_base": datos["inflacion"], "pi": datos["inflacion"], "crecimiento": datos["crecimiento"],
                "desempleo0": datos["desempleo"], "tasa": datos["tasa_politica"], "tasa0": datos["tasa_politica"],
                "nivel": 1.0, "tendencia": None, "gob": 0.0, "fijos_prev": 0.0, "indice": Indice(),
                "indice_val": 1000.0, "pib": 0.0,
            })
        R = len(self.regiones)

        # --- Agentes (estructura de arreglos) ---
        N = int(cfg["agentes"])
        pesos = np.sqrt([r["poblacion"] for r in self.regiones])
        cuotas = np.maximum(15, np.round(pesos / pesos.sum() * N)).astype(int)
        self.region = np.repeat(np.arange(R), cuotas)
        N = len(self.region) + 1  # +1 formador de liquidez
        self.region = np.append(self.region, 0)
        u = self.rng.random(N)
        self.tipo = np.where(u < 0.76, HOGAR, np.where(u < 0.96, INVERSIONISTA, BANCO)).astype(np.int8)
        for i in range(R):  # al menos un banco por región
            idx = np.flatnonzero((self.region == i) & (self.tipo != BANCO))
            if not (self.tipo[self.region == i] == BANCO).any():
                self.tipo[idx[0]] = BANCO
        self.creador = N - 1
        self.tipo[self.creador] = CREADOR
        self.pais_agente = np.array([self.regiones[r]["pais"] for r in self.region])
        sal_base = np.array([self.regiones[r]["salario"] for r in self.region])
        self.salario = sal_base * self.rng.lognormal(0.0, 0.35, N)
        self.aversion = self.rng.lognormal(0.2, 0.45, N)
        self.efectivo = np.where(self.tipo == HOGAR, self.salario * self.rng.lognormal(0.4, 0.8, N),
                                 sal_base * self.rng.lognormal(3.6, 0.7, N))
        self.deuda = np.zeros(N)
        self.empleo = np.full(N, -1, dtype=np.int64)

        # --- Empresas ---
        self.empresas: list[Empresa] = []
        self.pos: dict[str, np.ndarray] = {}
        self.libros: dict[str, LibroOrdenes] = {}
        self.contador = 0
        for ri, reg in enumerate(self.regiones):
            for k in range(cfg["empresas_por_region"]):
                sector = reg["sectores"][k % len(reg["sectores"])]
                candidatos = np.flatnonzero((self.region == ri) & (self.tipo == HOGAR))
                fundador = int(self.rng.choice(candidatos)) if len(candidatos) else -1
                self._crear_empresa(ri, sector, fundador, capital=None)
        # Empleo inicial según el desempleo observado de cada país.
        for ri, reg in enumerate(self.regiones):
            fuerza = np.flatnonzero((self.region == ri) & (self.tipo == HOGAR))
            emp_reg = [j for j, e in enumerate(self.empresas) if e.region == ri]
            if not emp_reg:
                continue
            ocup = fuerza[self.rng.random(len(fuerza)) > reg["desempleo0"] / 100]
            tam = self.rng.lognormal(0, 0.7, len(emp_reg))
            self.empleo[ocup] = self.rng.choice(emp_reg, size=len(ocup), p=tam / tam.sum())
        for j, e in enumerate(self.empresas):
            if e.fundador >= 0:
                self.empleo[e.fundador] = j
            nomina = self._nomina_mensual(j)
            e.capital = max(nomina, self.regiones[e.region]["salario"]) * self.rng.lognormal(2.3, 0.4)
            e.efectivo = 1.2 * max(nomina, 1.0)
            e.deuda = 0.35 * e.capital
            self._emitir(e, primera=True)
        # Bancos: liquidez para prestar.
        bancos = self.tipo == BANCO
        deuda_total = sum(e.deuda for e in self.empresas)
        self.efectivo[bancos] = 2.0 * deuda_total / bancos.sum()
        self.efectivo[self.creador] = 0.15 * sum(e.capital for e in self.empresas)
        # Exportaciones base: ~12% de la nómina de cada región.
        for ri, reg in enumerate(self.regiones):
            nomina = sum(self._nomina_mensual(j) for j, e in enumerate(self.empresas) if e.region == ri)
            reg["export_base"] = 0.12 * nomina / DIAS_MES
        for ri, reg in enumerate(self.regiones):
            reg["fijos_prev"] = sum(0.0015 * e.capital for e in self.empresas if e.region == ri)
        self._caps_previas = {i: None for i in range(R)}
        self.pendientes: dict[str, dict] = {}   # órdenes que este nodo envió a otros nodos
        self.extranjero: dict[str, float] = {}  # acciones en manos extranjeras, por ticker local
        self.bajas = deque(maxlen=200)
        self.vela_actual: dict = {}

    # ------------------------------------------------------------------ utilidades
    def __getstate__(self):
        d = dict(self.__dict__)
        d["paralelo"] = None
        return d

    def _nomina_mensual(self, j):
        return float(self.salario[self.empleo == j].sum())

    def fx(self, desde: str, hacia: str) -> float:
        if desde == hacia:
            return 1.0
        return self.trm if (desde, hacia) == ("USD", "COP") else 1.0 / self.trm

    def evento(self, tipo, texto, region=None):
        self.eventos.append({"t": self.t, "nodo": self.id, "tipo": tipo, "texto": texto,
                             "region": self.regiones[region]["codigo"] if region is not None else None})

    def _crear_empresa(self, ri, sector, fundador, capital):
        reg = self.regiones[ri]
        self.contador += 1
        ticker = f"{reg['codigo']}.{sector}{self.contador}"
        e = Empresa(ticker=ticker, region=ri, sector=sector, efectivo=capital or 0.0, capital=capital or 0.0,
                    deuda=0.0, productividad=float(self.rng.lognormal(0, 0.15)),
                    acciones=1_000_000.0 if self.moneda == "COP" else 10_000.0,
                    fundador=fundador, nacida=self.t)
        self.empresas.append(e)
        if fundador >= 0 and self.tipo[fundador] == HOGAR:
            self.tipo[fundador] = EMPRESARIO
        return e

    def _emitir(self, e: Empresa, primera=False):
        """Crea el libro de órdenes y reparte las acciones iniciales."""
        precio = max(e.patrimonio, 1.0) / e.acciones
        N = len(self.tipo)
        p = np.zeros(N)
        if primera:
            dueno = 0.35
            inversores = np.flatnonzero(np.isin(self.tipo, (INVERSIONISTA, BANCO)))
            elegidos = self.rng.choice(inversores, size=min(8, len(inversores)), replace=False)
            p[elegidos] += e.acciones * 0.57 / len(elegidos)
            p[self.creador] += e.acciones * 0.08
        else:
            dueno = 1.0
        if e.fundador >= 0:
            p[e.fundador] += e.acciones * dueno
        else:
            p[self.creador] += e.acciones * dueno
        self.pos[e.ticker] = p
        self.libros[e.ticker] = LibroOrdenes(e.ticker, precio)
        e.precios.extend([precio] * 2)

    def fundamental(self, e: Empresa):
        roe = e.utilidad_anual / max(e.patrimonio, 0.1 * e.capital, 1.0)
        valor = max(e.patrimonio, 0.05 * e.capital) * (1 + 2 * float(np.clip(roe, -0.4, 0.4)))
        return max(0.02 * self.libros[e.ticker].ultimo, valor / e.acciones)

    # ------------------------------------------------------------------ tick
    def paso(self, t: int, macro: dict, ordenes_in: list, fills_in: list, catalogo: dict, choques: list):
        self.t = t
        self.eventos = []
        self.flujo_usd = 0.0  # salida neta de capital de Colombia hacia el exterior en este tick (USD)
        rng = self.rng
        R = len(self.regiones)
        ef = self._efectos(choques)
        self.trm = macro.get("trm", self.trm)
        self.trm_hist.append(self.trm)
        for f in fills_in:
            self._liquidar_fill(f)
        self._expirar_pendientes()

        # Tasas de interés por región.
        for reg in self.regiones:
            if self.pais == "INT":
                reg["tasa"] = macro.get("tasas", {}).get(reg["codigo"], reg["tasa"])
            else:
                reg["tasa"] = macro.get("tasa", reg["tasa"])
            reg["tasa"] += ef["tasa_delta"]
        tasa_ag = np.array([self.regiones[r]["tasa"] for r in self.region])
        spread = np.array([self.regiones[r]["reglas"]["spread_prestamo"] for r in self.region])
        tasa_prest_ag = tasa_ag / 100 + spread
        nivel_ag = np.array([self.regiones[r]["nivel"] for r in self.region])

        # 1) Salarios e impuestos a personas.
        n_emp = len(self.empresas)
        ocupado = self.empleo >= 0
        pago = np.where(ocupado, self.salario * nivel_ag / DIAS_MES * ef["productividad"], 0.0)
        nomina = np.bincount(self.empleo[ocupado], weights=pago[ocupado], minlength=n_emp)
        imp_p = np.array([self.regiones[r]["reglas"]["impuesto_renta_personas"] for r in self.region])
        neto = pago * (1 - imp_p)
        recaudo_p = np.bincount(self.region, weights=pago * imp_p, minlength=R)
        fuerza = (self.tipo == HOGAR) | (self.tipo == EMPRESARIO)
        desocupado = fuerza & ~ocupado
        base_ag = np.array([self.regiones[r]["salario"] for r in self.region])
        subs = np.array([self.regiones[r]["reglas"]["subsidio_desempleo"] for r in self.region])
        subsidio = np.where(desocupado, subs * base_ag * nivel_ag / DIAS_MES, 0.0)
        ingreso = neto + subsidio
        self.efectivo += ingreso
        subsidio_reg = np.bincount(self.region, weights=subsidio, minlength=R)

        # 2) Intereses de hogares a bancos.
        int_hog = self.deuda * tasa_prest_ag / DIAS_ANIO
        self.efectivo -= int_hog
        ingreso_bancos = int_hog.sum()

        # 3) Consumo (con efecto de la tasa de interés y de los choques).
        prop = np.array([self.regiones[r]["reglas"]["propension_consumo"] for r in self.region])
        tasa0_ag = np.array([self.regiones[r]["tasa0"] for r in self.region])
        prop = np.clip(prop * (1 - 0.02 * (tasa_ag - tasa0_ag)), 0.5, 1.0) * ef["consumo"]
        reserva = 2 * base_ag * nivel_ag
        riqueza_libre = np.maximum(self.efectivo - reserva, 0)
        tasa_riqueza = np.where(self.tipo == HOGAR, 0.004, np.where(self.tipo == EMPRESARIO, 0.002, 0.0008))
        tasa_riqueza[(self.tipo == BANCO) | (self.tipo == CREADOR)] = 0.0
        consumo = prop * ingreso + tasa_riqueza * riqueza_libre * ef["consumo"]
        consumo[(self.tipo == BANCO) | (self.tipo == CREADOR)] = 0.0
        self.efectivo -= consumo
        consumo_reg = np.bincount(self.region, weights=consumo, minlength=R)

        # 4) Demanda por región: consumo doméstico (menos importaciones) + gobierno + insumos + exportaciones.
        demanda_ext = macro.get("demanda_externa", 1.0) * ef["demanda_ext"]
        petroleo = macro.get("petroleo_rel", 1.0)
        trm_rel = self.trm / self.trm0
        D_dom = np.zeros(R)
        D_exp = np.zeros(R)
        for ri, reg in enumerate(self.regiones):
            gob_gasto = max(reg["gob"], 0) * 0.9
            reg["gob"] -= gob_gasto
            importaciones = consumo_reg[ri] * 0.15
            D_dom[ri] = consumo_reg[ri] - importaciones + gob_gasto + reg["fijos_prev"]
            # Exportaciones: en equilibrio compensan las importaciones; se mueven con la demanda
            # externa, la TRM (para Colombia) o el crecimiento del país (mercado internacional).
            reg["import_ema"] = 0.98 * reg.get("import_ema", importaciones) + 0.02 * importaciones
            if self.moneda == "COP":
                factor = demanda_ext * trm_rel ** 0.5
            else:
                factor = (1 + reg["crecimiento"] / 100 / DIAS_ANIO * 21) * ef["demanda_ext"]
            D_exp[ri] = reg["import_ema"] * factor
            reg["gob"] += recaudo_p[ri] - subsidio_reg[ri]

        # 5) Ventas, costos, impuestos y crédito de las empresas.
        vivas = [j for j, e in enumerate(self.empresas) if e.viva]
        empleados = np.bincount(self.empleo[ocupado], minlength=n_emp)
        fijos_reg = np.zeros(R)
        liquidez = self.efectivo[self.tipo == BANCO].sum() * ef["credito"]
        prestado = 0.0
        quiebras_t, nuevas_t = 0, 0
        for ri, reg in enumerate(self.regiones):
            js = [j for j in vivas if self.empresas[j].region == ri]
            if not js:
                continue
            cap = np.array([self.empresas[j].productividad * (empleados[j] + 0.5) ** 0.9 for j in js])
            w = cap * rng.lognormal(0, 0.15, len(js))
            ventas = D_dom[ri] * w / w.sum()
            exp_w = np.array([
                (3.0 if self.empresas[j].sector in SECTORES_EXPORTADORES else 0.3)
                * (petroleo if self.empresas[j].sector in SECTORES_PETROLEO else 1.0) for j in js]) * w
            ventas = ventas + D_exp[ri] * exp_w / exp_w.sum()
            renta = reg["reglas"]["renta_empresas"]
            tasa_prest = reg["tasa"] / 100 + reg["reglas"]["spread_prestamo"]
            for j, v in zip(js, ventas):
                e = self.empresas[j]
                fijos = 0.0015 * e.capital
                interes = e.deuda * tasa_prest / DIAS_ANIO
                utilidad = v - nomina[j] - fijos - interes
                impuesto = renta * utilidad if utilidad > 0 else 0.0
                e.efectivo += v - nomina[j] - fijos - interes - impuesto
                e.ingresos, e.utilidad = v, utilidad - impuesto
                e.util_mes.append(e.utilidad)
                e.util_ema = e.utilidad if len(e.util_mes) == 1 else 0.98 * e.util_ema + 0.02 * e.utilidad
                e.perdidas = e.perdidas + 1 if utilidad < 0 else 0
                reg["gob"] += impuesto
                ingreso_bancos += interes
                fijos_reg[ri] += fijos
                e.productividad *= math.exp(rng.normal(-0.0002, 0.008))
                if e.utilidad > 0:
                    e.capital += 0.25 * e.utilidad
                # Crédito o quiebra.
                if e.perdidas > 60 and e.patrimonio < 0:
                    self._quebrar(j)
                    quiebras_t += 1
                    continue
                if e.efectivo < 0:
                    necesidad = -e.efectivo + 10 * nomina[j]
                    limite = reg["reglas"]["apalancamiento_max"] * max(e.capital, 0) * ef["credito"]
                    if e.deuda + necesidad <= limite and prestado + necesidad <= liquidez:
                        e.deuda += necesidad
                        e.efectivo += necesidad
                        prestado += necesidad
                    else:
                        self._quebrar(j)
                        quiebras_t += 1
                        continue
                elif e.deuda > 0 and e.efectivo > 60 * nomina[j]:
                    pago_d = min(e.deuda, 0.02 * e.efectivo)
                    e.deuda -= pago_d
                    e.efectivo -= pago_d
                    prestado -= pago_d
                # Contratar o despedir según las ventas: plantilla objetivo = ventas / costo laboral.
                sal_dia = reg["salario"] * reg["nivel"] / DIAS_MES
                e.ventas_prom = v if e.ventas_prom == 0 else 0.95 * e.ventas_prom + 0.05 * v
                objetivo = e.ventas_prom * 0.69 / max(sal_dia, 1e-9)
                if empleados[j] < objetivo - 0.5 and e.efectivo > 20 * max(nomina[j], sal_dia) and rng.random() < 0.15:
                    libres = np.flatnonzero(desocupado & (self.region == ri))
                    if len(libres):
                        k = int(rng.choice(libres))
                        self.empleo[k] = j
                        desocupado[k] = False
                elif empleados[j] > max(objetivo * 1.15, 1) and rng.random() < 0.10:
                    trab = np.flatnonzero((self.empleo == j) & (np.arange(len(self.empleo)) != e.fundador))
                    if len(trab):
                        k = int(rng.choice(trab))
                        self.empleo[k] = -1
                        desocupado[k] = fuerza[k]
            reg["fijos_prev"] = fijos_reg[ri]
        bancos = np.flatnonzero(self.tipo == BANCO)
        self.efectivo[bancos] += (ingreso_bancos - prestado) / len(bancos)

        # Rotación laboral: algunas personas pierden o dejan su empleo cada día.
        fundadores = np.array([e.fundador for e in self.empresas if e.viva and e.fundador >= 0], dtype=int)
        sale = (self.empleo >= 0) & (rng.random(len(self.tipo)) < 0.0025)
        sale[fundadores] = False
        self.empleo[sale] = -1

        # 6) Hogares endeudados y quiebras personales.
        rojo = self.efectivo < 0
        prestamo_hogares = -self.efectivo[rojo].sum()
        self.deuda[rojo] += -self.efectivo[rojo]
        self.efectivo[bancos] -= prestamo_hogares / len(bancos)
        self.efectivo[rojo] = 0.0
        limite_p = 8 * np.maximum(self.salario, base_ag) * nivel_ag
        quiebra_p = self.deuda > limite_p
        if quiebra_p.any():
            n = int(quiebra_p.sum())
            self.totales["quiebras_personales"] += n
            self.totales["perdidas_banca"] += float(self.deuda[quiebra_p].sum())
            self.deuda[quiebra_p] = 0.0
            if n:
                self.evento("quiebra_personal", f"{n} persona(s) se declaran en insolvencia")
        paga = (self.deuda > 0) & (self.efectivo > 3 * base_ag * nivel_ag)
        abono = np.minimum(self.deuda, 0.05 * self.efectivo) * paga
        self.deuda -= abono
        self.efectivo -= abono
        self.efectivo[bancos] += abono.sum() / len(bancos)

        # 7) Dividendos mensuales.
        if t % DIAS_MES == 0:
            for e in self.empresas:
                u_mes = sum(e.util_mes)
                if e.viva and u_mes > 0 and e.efectivo > 0.6 * u_mes:
                    div = 0.4 * u_mes
                    e.efectivo -= div
                    p = self.pos[e.ticker]
                    self.efectivo += div * p / e.acciones

        # 8) Emprendimiento.
        prob = np.array([self.regiones[r]["reglas"]["prob_emprender"] for r in self.region])
        apto = ((self.tipo == HOGAR) & (self.efectivo > 6 * base_ag * nivel_ag)) | \
               ((self.tipo == INVERSIONISTA) & (self.efectivo > 20 * base_ag * nivel_ag))
        quiere = apto & (rng.random(len(self.tipo)) < prob / self.aversion * (1 + 2 * desocupado))
        for k in np.flatnonzero(quiere)[:2]:
            ri = int(self.region[k])
            reg = self.regiones[ri]
            aporte = 0.6 * self.efectivo[k]
            self.efectivo[k] -= aporte
            sector = str(rng.choice(reg["sectores"]))
            e = self._crear_empresa(ri, sector, int(k), capital=aporte)
            e.efectivo, e.capital = aporte * 0.5, aporte * 0.5
            j = len(self.empresas) - 1
            if self.tipo[k] == EMPRESARIO:
                self.empleo[k] = j
            libres = np.flatnonzero(desocupado & (self.region == ri))
            for c in libres[:2]:
                self.empleo[c] = j
            self._emitir(e)
            nuevas_t += 1
            self.totales["nuevas"] += 1
            self.evento("nueva_empresa", f"Nace {e.ticker} ({sector}) en {reg['nombre']}", ri)

        # 9) Inflación y nivel de precios.
        for ri, reg in enumerate(self.regiones):
            D = D_dom[ri] + D_exp[ri]
            reg["tendencia"] = D if reg["tendencia"] is None else 0.99 * reg["tendencia"] + 0.01 * D
            brecha = D / max(reg["tendencia"], 1e-9) - 1
            dtrm = math.log(self.trm_hist[-1] / self.trm_hist[0]) * 12 * 100 if self.moneda == "COP" else 0.0
            objetivo = reg["pi_base"] + 15 * float(np.clip(brecha, -0.15, 0.15)) + 0.1 * dtrm - 0.3 * (reg["tasa"] - reg["tasa0"]) + ef["inflacion"]
            reg["pi"] = float(np.clip(0.97 * reg["pi"] + 0.03 * objetivo, -5, 60))
            reg["nivel"] *= 1 + reg["pi"] / 100 / DIAS_ANIO
            reg["pib"] = D

        # 10) Mercado de acciones.
        salientes, fills_out = self._mercado(ordenes_in, catalogo, ef)
        self.totales["quiebras"] += quiebras_t
        return {
            "estado": self._estado(quiebras_t, nuevas_t, empleados, fuerza, desocupado),
            "ordenes": salientes,
            "fills": fills_out,
            "eventos": self.eventos,
        }

    def _efectos(self, choques):
        ef = {"consumo": 1.0, "demanda_ext": 1.0, "credito": 1.0, "mu": 0.0, "vol": 1.0,
              "tasa_delta": 0.0, "productividad": 1.0, "inflacion": 0.0}
        for c in choques:
            if c.get("objetivo") not in (None, "", "todos", self.id):
                continue
            m = float(c.get("magnitud", 1.0))
            tipo = c["tipo"]
            if tipo == "crisis_financiera":
                ef["credito"] *= max(0.1, 1 - 0.5 * m); ef["mu"] -= 0.004 * m; ef["vol"] *= 1 + m
            elif tipo == "pandemia":
                ef["consumo"] *= max(0.3, 1 - 0.3 * m); ef["productividad"] *= max(0.5, 1 - 0.15 * m)
            elif tipo == "crisis_internacional":
                ef["demanda_ext"] *= max(0.2, 1 - 0.3 * m); ef["mu"] -= 0.002 * m; ef["vol"] *= 1 + 0.5 * m
            elif tipo == "boom_consumo":
                ef["consumo"] *= 1 + 0.2 * m; ef["mu"] += 0.002 * m
            elif tipo == "inflacion":
                ef["inflacion"] += 5 * m
        return ef

    def _quebrar(self, j):
        e = self.empresas[j]
        e.viva = False
        self.totales["perdidas_banca"] += max(e.deuda - max(e.efectivo, 0), 0)
        self.empleo[self.empleo == j] = -1
        if e.fundador >= 0 and self.tipo[e.fundador] == EMPRESARIO:
            self.tipo[e.fundador] = HOGAR
        self.pos[e.ticker][:] = 0
        self.libros.pop(e.ticker, None)
        self.extranjero.pop(e.ticker, None)
        self.bajas.append(e.ticker)
        self.evento("quiebra", f"Quiebra {e.ticker}: deuda {e.deuda:,.0f} {self.moneda}", e.region)

    # ------------------------------------------------------------------ mercado
    def _mercado(self, ordenes_in, catalogo, ef):
        rng = self.rng
        for lib in self.libros.values():
            lib.nuevo_tick()
        locales = [e for e in self.empresas if e.viva]
        por_ticker = {e.ticker: e for e in locales}
        ordenes: list[Orden] = []

        # Formador de liquidez: cotiza compra y venta alrededor del valor fundamental.
        c = self.creador
        quotes = []
        for e in locales:
            lib = self.libros[e.ticker]
            inventario = self.pos[e.ticker][c] / e.acciones
            centro = lib.ultimo * (1 + 0.03 * (self.fundamental(e) / lib.ultimo - 1)) * (1 - 0.3 * (inventario - 0.08))
            for paso_p, frac in ((0.002, 0.0008), (0.012, 0.0015), (0.03, 0.003)):  # tres niveles de profundidad
                q = max(1.0, frac * e.acciones)
                qv = min(q, self.pos[e.ticker][c])
                if qv >= 1:
                    self.pos[e.ticker][c] -= qv
                    quotes.append(Orden(self.id, c, e.ticker, -1, qv, centro * (1 + paso_p), pais=self.pais))
                costo = q * centro * (1 - paso_p)
                if self.efectivo[c] > costo:
                    self.efectivo[c] -= costo
                    quotes.append(Orden(self.id, c, e.ticker, 1, q, centro * (1 - paso_p), pais=self.pais))

        # Activos candidatos: locales primero, luego los del catálogo de otros nodos.
        tickers = [e.ticker for e in locales]
        mon = [self.moneda] * len(tickers)
        precios, mus, sigs = [], [], []
        tasa_ref = np.mean([r["tasa"] for r in self.regiones]) / 100
        for e in locales:
            p = self.libros[e.ticker].ultimo
            hist = np.array(e.precios)
            rets = np.diff(np.log(hist)) if len(hist) > 2 else np.zeros(1)
            mom = math.log(hist[-1] / hist[0]) if len(hist) > 1 else 0.0
            ey = float(np.clip(e.utilidad_anual / (p * e.acciones), -0.5, 0.5))
            mus.append(0.25 * (ey - tasa_ref) / DIAS_ANIO + 0.1 * mom / 20
                       + 0.3 * math.log(self.fundamental(e) / p) / 20 + ef["mu"])
            sigs.append(float(np.clip(rets.std() if len(rets) > 1 else 0.02, 0.008, 0.08)) * ef["vol"])
            precios.append(p)
        n_local = len(tickers)
        for tk, a in catalogo.items():
            if a["nodo"] == self.id or tk in por_ticker:
                continue
            tickers.append(tk)
            mon.append(a["mon"])
            precios.append(a["p"] * self.fx(a["mon"], self.moneda))
            mus.append(a["mu"] + ef["mu"])
            sigs.append(a["sig"] * ef["vol"])
        precios = np.array(precios)

        # Participantes: inversionistas, bancos, empresarios y hogares con ahorro (35% actúa cada día).
        base = np.array([self.regiones[r]["salario"] * self.regiones[r]["nivel"] for r in self.region])
        elegible = np.isin(self.tipo, (INVERSIONISTA, BANCO, EMPRESARIO)) | \
                   ((self.tipo == HOGAR) & (self.efectivo > 3 * base))
        elegible[self.creador] = False
        part = np.flatnonzero(elegible & (rng.random(len(self.tipo)) < 0.35))
        if len(tickers) and len(part):
            presupuesto = np.where(self.tipo[part] == BANCO, 0.15, 1.0) * self.efectivo[part]
            posiciones = np.column_stack([self.pos.get(tk, np.zeros(len(self.tipo)))[part] for tk in tickers])
            dec = self.paralelo.decidir(presupuesto, self.aversion[part], posiciones, precios,
                                        np.array(mus), np.array(sigs), n_local,
                                        semilla=int(rng.integers(1 << 30)))
            for fila in dec:
                ag = int(part[int(fila[0])])
                ai, lado, qty, lim_local = int(fila[1]), int(fila[2]), float(fila[3]), float(fila[4])
                tk = tickers[ai]
                fx = self.fx(mon[ai], self.moneda)
                lim = lim_local / fx
                if ai < n_local:
                    impuesto = 0.0
                    reg_pais = self.regiones[por_ticker[tk].region]["pais"]
                    if reg_pais != self.pais_agente[ag]:
                        impuesto = self.regiones[por_ticker[tk].region]["reglas"]["impuesto_transaccion_extranjeros"]
                else:
                    a = catalogo[tk]
                    impuesto = a.get("itx", 0.0) if a.get("pais") != self.pais_agente[ag] else 0.0
                if lado > 0:
                    reserva = qty * lim_local * (1 + impuesto) * (1.03 if ai >= n_local else 1.0)
                    if reserva > self.efectivo[ag]:
                        continue
                    self.efectivo[ag] -= reserva
                else:
                    qty = min(qty, self.pos[tk][ag])
                    if qty < 1:
                        continue
                    self.pos[tk][ag] -= qty
                    reserva = qty
                o = Orden(self.id, ag, tk, lado, qty, lim, pais=str(self.pais_agente[ag]))
                self.refs += 1
                o.ref = f"{self.id}-{self.refs}"
                if ai < n_local:
                    o.reserva, o.impuesto = reserva, impuesto
                    ordenes.append(o)
                else:
                    self.pendientes[o.ref] = {"agente": ag, "ticker": tk, "lado": lado, "qty": qty,
                                              "reserva": reserva, "impuesto": impuesto, "t": self.t,
                                              "nodo": catalogo[tk]["nodo"]}
                    if tk not in self.pos:
                        self.pos[tk] = np.zeros(len(self.tipo))
                    ordenes.append(o)

        # Operadores de ruido (cero inteligencia): pequeñas órdenes aleatorias que dan liquidez y vida al precio.
        candidatos = np.flatnonzero(elegible)
        if len(candidatos):
            for e in locales:
                lib = self.libros[e.ticker]
                for _ in range(rng.poisson(4)):
                    ag = int(rng.choice(candidatos))
                    lim = lib.ultimo * math.exp(rng.normal(0, 0.012 * ef["vol"]) + ef["mu"])
                    qty = float(max(1, round(e.acciones * rng.uniform(0.0001, 0.0006))))
                    if rng.random() < 0.5:
                        reserva = qty * lim
                        if reserva > 0.2 * self.efectivo[ag]:
                            continue
                        self.efectivo[ag] -= reserva
                        lado = 1
                    else:
                        qty = min(qty, self.pos[e.ticker][ag])
                        if qty < 1:
                            continue
                        self.pos[e.ticker][ag] -= qty
                        reserva, lado = qty, -1
                    o = Orden(self.id, ag, e.ticker, lado, qty, lim, pais=str(self.pais_agente[ag]))
                    o.reserva = reserva
                    ordenes.append(o)

        # Órdenes que llegaron de otros nodos (validadas con las reglas locales).
        fills_out: dict[str, list] = {}
        remotas = []
        for d in ordenes_in:
            e = por_ticker.get(d["tk"])
            o = Orden(d["nodo"], d["ag"], d["tk"], d["lado"], d["qty"], d["lim"], ref=d["ref"], pais=d["pais"])
            if e is None:
                fills_out.setdefault(o.nodo, []).append(self._fill(o, "no_listado"))
                continue
            reg = self.regiones[e.region]
            if o.lado > 0 and o.pais != reg["pais"]:
                tope = reg["reglas"]["max_extranjeros"] * e.acciones - self.extranjero.get(e.ticker, 0.0)
                o.qty = min(o.qty, max(tope, 0.0))
                if o.qty < 1:
                    fills_out.setdefault(o.nodo, []).append(self._fill(o, "tope_extranjeros"))
                    continue
            remotas.append(o)

        locales_y_remotas = [o for o in ordenes if o.ticker in self.libros] + remotas
        salientes: dict[str, list] = {}
        for o in ordenes:
            if o.ticker not in self.libros:
                salientes.setdefault(self.pendientes[o.ref]["nodo"], []).append(
                    {"nodo": self.id, "ag": o.agente, "tk": o.ticker, "lado": o.lado, "qty": o.qty,
                     "lim": o.limite, "ref": o.ref, "pais": o.pais})
        for q in quotes:
            self.libros[q.ticker].enviar(q)
        orden_aleatorio = rng.permutation(len(locales_y_remotas))
        for i in orden_aleatorio:
            o = locales_y_remotas[i]
            self.libros[o.ticker].enviar(o)

        # Liquidación de lo ejecutado.
        for o in quotes:
            self._liquidar_local(o, o.limite * o.qty if o.lado > 0 else o.qty, 0.0)
        for o in locales_y_remotas:
            if o.nodo == self.id:
                self._liquidar_local(o, o.reserva, o.impuesto)
            else:
                fills_out.setdefault(o.nodo, []).append(self._fill(o))
                if self.moneda == "USD" and o.pais == "COL":
                    self.flujo_usd += o.lado * o.costo
            e = por_ticker[o.ticker]
            if o.pais != self.regiones[e.region]["pais"] and o.lleno > 0:
                self.extranjero[o.ticker] = self.extranjero.get(o.ticker, 0.0) + o.lado * o.lleno

        self.vela_actual = {}
        for e in locales:
            lib = self.libros[e.ticker]
            e.precios.append(lib.ultimo)
            self.vela_actual[e.ticker] = lib.vela()
        return salientes, fills_out

    def _fill(self, o: Orden, motivo: str = ""):
        return {"ref": o.ref, "lleno": o.lleno, "costo": o.costo, "mon": self.moneda, "motivo": motivo}

    def _liquidar_local(self, o: Orden, reserva, impuesto):
        tk = o.ticker
        if tk not in self.pos:
            return
        if o.lado > 0:
            self.pos[tk][o.agente] += o.lleno
            self.efectivo[o.agente] += reserva - o.costo * (1 + impuesto)
        else:
            self.efectivo[o.agente] += o.costo * (1 - impuesto)
            self.pos[tk][o.agente] += o.qty - o.lleno

    def _liquidar_fill(self, f):
        p = self.pendientes.pop(f["ref"], None)
        if p is None:
            return
        ag, tk = p["agente"], p["ticker"]
        if tk not in self.pos:
            self.pos[tk] = np.zeros(len(self.tipo))
        fx = self.fx(f["mon"], self.moneda)
        if self.moneda == "USD" and f["mon"] == "COP":
            self.flujo_usd -= p["lado"] * f["costo"] / self.trm
        if p["lado"] > 0:
            self.pos[tk][ag] += f["lleno"]
            self.efectivo[ag] += p["reserva"] - f["costo"] * fx * (1 + p["impuesto"])
        else:
            self.efectivo[ag] += f["costo"] * fx * (1 - p["impuesto"])
            self.pos[tk][ag] += p["qty"] - f["lleno"]

    def _expirar_pendientes(self, ticks=20):
        """Tolerancia a fallos: si el nodo destino no respondió, se devuelve la reserva."""
        for ref in [r for r, p in self.pendientes.items() if self.t - p["t"] > ticks]:
            self._liquidar_fill({"ref": ref, "lleno": 0.0, "costo": 0.0, "mon": self.moneda})

    def aplicar_bajas(self, tickers):
        """Acciones de empresas de otros nodos que quebraron: valen cero."""
        for tk in tickers:
            if tk in self.pos and tk not in self.libros:
                self.pos[tk][:] = 0

    # ------------------------------------------------------------------ estado publicado
    def _estado(self, quiebras_t, nuevas_t, empleados, fuerza, desocupado):
        activos = {}
        caps_reg = np.zeros(len(self.regiones))
        nuevas_reg = np.zeros(len(self.regiones))
        tasa_ref = np.mean([r["tasa"] for r in self.regiones]) / 100
        for e in self.empresas:
            if not e.viva:
                continue
            lib = self.libros[e.ticker]
            v = self.vela_actual.get(e.ticker) or lib.vela()
            hist = np.array(e.precios)
            rets = np.diff(np.log(hist)) if len(hist) > 2 else np.zeros(1)
            mom = math.log(hist[-1] / hist[0]) if len(hist) > 1 else 0.0
            ey = float(np.clip(e.utilidad_anual / (lib.ultimo * e.acciones), -0.5, 0.5))
            reg = self.regiones[e.region]
            activos[e.ticker] = {
                **{k: round(float(x), 6) for k, x in v.items()},
                "p": round(lib.ultimo, 6), "mon": self.moneda, "reg": reg["codigo"], "sec": e.sector,
                "pais": reg["pais"], "nodo": self.id, "cap": round(lib.ultimo * e.acciones, 2),
                "mu": round(0.25 * (ey - tasa_ref) / DIAS_ANIO + 0.1 * mom / 20
                            + 0.3 * math.log(self.fundamental(e) / lib.ultimo) / 20, 6),
                "sig": round(float(np.clip(rets.std() if len(rets) > 1 else 0.02, 0.008, 0.08)), 5),
                "itx": reg["reglas"]["impuesto_transaccion_extranjeros"],
            }
            caps_reg[e.region] += lib.ultimo * e.acciones
            if e.nacida == self.t:
                nuevas_reg[e.region] += lib.ultimo * e.acciones
        regiones = {}
        for ri, reg in enumerate(self.regiones):
            previas = self._caps_previas[ri]
            reg["indice_val"] = reg["indice"].valor(previas or caps_reg[ri], caps_reg[ri], nuevas_reg[ri])
            self._caps_previas[ri] = caps_reg[ri]
            f = fuerza & (self.region == ri)
            regiones[reg["codigo"]] = {
                "nombre": reg["nombre"], "pais": reg["pais"], "indice": round(reg["indice_val"], 3),
                "inflacion": round(reg["pi"], 3), "tasa": round(reg["tasa"], 3),
                "desempleo": round(100 * (desocupado & f).sum() / max(f.sum(), 1), 2),
                "pib": round(reg["pib"], 2), "empresas": sum(1 for e in self.empresas if e.viva and e.region == ri),
                "nivel_precios": round(reg["nivel"], 5),
            }
        valor = np.zeros(len(self.tipo))
        for tk, p in self.pos.items():
            if tk in self.libros:
                valor += p * self.libros[tk].ultimo
        riqueza = self.efectivo + valor - self.deuda
        personas = np.isin(self.tipo, (HOGAR, EMPRESARIO, INVERSIONISTA))
        pib = sum(r["pib"] for r in self.regiones)
        ind = {
            "pib": round(pib, 2),
            "inflacion": round(sum(r["pi"] * r["pib"] for r in self.regiones) / max(pib, 1e-9), 3),
            "desempleo": round(100 * desocupado.sum() / max(fuerza.sum(), 1), 2),
            "tasa": round(float(np.mean([r["tasa"] for r in self.regiones])), 3),
            "empresas": len(activos), "quiebras_t": quiebras_t, "nuevas_t": nuevas_t,
            **{k: (round(v, 2) if isinstance(v, float) else v) for k, v in self.totales.items()},
            "riqueza": round(float(riqueza[personas].sum()), 2), "gini": round(gini(riqueza[personas]), 4),
            "credito": round(float(self.deuda.sum() + sum(e.deuda for e in self.empresas if e.viva)), 2),
            "agentes": int(len(self.tipo)),
            "por_tipo": {TIPOS[i]: int((self.tipo == i).sum()) for i in range(len(TIPOS))},
            "pendientes_remotas": len(self.pendientes),
            "indice": round(float(np.mean([r["indice_val"] for r in self.regiones])), 3),
        }
        return {"t": self.t, "nodo": self.id, "nombre": self.cfg["nombre"], "pais": self.pais,
                "moneda": self.moneda, "activos": activos, "bajas": list(self.bajas)[-50:],
                "regiones": regiones, "ind": ind}
