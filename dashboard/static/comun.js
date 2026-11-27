// Utilidades compartidas por el panel general y las vistas de cada nodo.
const $ = (s, r = document) => r.querySelector(s);
const NODOS = ["tunja", "capitales", "departamentos", "colombia", "internacional"];
const NOMBRE = { coordinador: "Reloj global", tunja: "Tunja", capitales: "Capitales", departamentos: "Departamentos",
                 colombia: "Colombia", internacional: "Internacional" };
const COLOR = { tunja: "#f5a524", capitales: "#3b82f6", departamentos: "#16c784", colombia: "#ef4444", internacional: "#a78bfa" };
const ISO_NUM = { USA: "840", CHN: "156", BRA: "076", MEX: "484", DEU: "276", JPN: "392", GBR: "826", CHL: "152", PER: "604", COL: "170" };
const ISO2 = { USA: "US", CHN: "CN", BRA: "BR", MEX: "MX", DEU: "DE", JPN: "JP", GBR: "GB", CHL: "CL", PER: "PE" };
const DEP_COD = { BOY: "15", ANT: "05", VAL: "76", CUN: "25", SAN: "68", MET: "50", NAR: "52", ATL: "08" };
const COD_DEP = Object.fromEntries(Object.entries(DEP_COD).map(([k, v]) => [v, k]));
const SECTORES = { COM: "Comercio", EDU: "Educación", CON: "Construcción", SAL: "Salud", TUR: "Turismo", AGR: "Agro",
  TRA: "Transporte", ALI: "Alimentos", FIN: "Finanzas", TEC: "Tecnología", TEX: "Textil", PUE: "Puertos", ENE: "Energía",
  PET: "Petróleo", MIN: "Minería", CAF: "Café", AZU: "Azúcar", FLO: "Flores", GAN: "Ganadería", TEL: "Telecom",
  CEM: "Cemento", MAN: "Manufactura", AUT: "Automotriz", QUI: "Química", PES: "Pesca" };

// ---------- formato ----------
// Intl.NumberFormat en caché: toLocaleString crea un formateador nuevo en cada llamada (muy lento con cientos de celdas).
const _fmts = {};
const fmt = (x, d = 2) => (x == null || isNaN(x)) ? "—" :
  (_fmts[d] || (_fmts[d] = new Intl.NumberFormat("es-CO", { minimumFractionDigits: d, maximumFractionDigits: d }))).format(x);
const pct = (x, d = 2) => (x == null || isNaN(x)) ? "—" : (x >= 0 ? "+" : "") + (100 * x).toFixed(d) + "%";
const clase = (x) => x > 0 ? "sube" : x < 0 ? "baja" : "";
const corto = (x) => { const a = Math.abs(x || 0); return a >= 1e12 ? fmt(x / 1e12, 1) + " B" : a >= 1e9 ? fmt(x / 1e9, 1) + " MM" : a >= 1e6 ? fmt(x / 1e6, 1) + " M" : a >= 1e3 ? fmt(x / 1e3, 1) + " k" : fmt(x, 0); };
const decimales = (a) => a && a.mon === "USD" ? 2 : 1;
// Ejecuta fn como mucho una vez cada `ms` (y solo cuando la pestaña está visible, vía requestAnimationFrame).
// Los datos se actualizan en cada mensaje; lo que es caro de pintar (tablas, mapas) se pinta con este ritmo.
function limitar(fn, ms) {
  let ultimo = 0, pendiente = false;
  const correr = () => { pendiente = false; ultimo = performance.now(); fn(); };
  return (forzar) => {
    if (forzar) return correr();
    if (pendiente) return;
    pendiente = true;
    const espera = Math.max(0, ms - (performance.now() - ultimo));
    setTimeout(() => requestAnimationFrame(correr), espera);
  };
}
// Dos SVG apilados con el mismo viewBox: el de abajo (geografía, estático) no se vuelve a pintar cuando
// se animan las líneas/pulsos del de arriba. Antes todo estaba en un solo SVG y el navegador repintaba
// cientos de polígonos 60 veces por segundo.
function capasMapa(el, W, H) {
  const base = d3.select(el).append("svg").attr("viewBox", `0 0 ${W} ${H}`).attr("class", "svg-mapa");
  const arriba = d3.select(el).append("svg").attr("viewBox", `0 0 ${W} ${H}`).attr("class", "svg-mapa svg-capa");
  _capas.push(arriba.node());
  return { base, arriba };
}
// Mueve las líneas punteadas de flujo a 12 cuadros por segundo, solo en la capa animada y con la pestaña visible.
const _capas = [];
(function animarFlujos() {
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  let k = 0;
  setInterval(() => {
    if (document.hidden || !_capas.length) return;
    k++;
    for (const c of _capas) {
      if (!c._tieneFlujos && !(c._tieneFlujos = !!c.querySelector(".flujo, .enlace-mundo"))) continue;
      c.style.setProperty("--f1", (-(k * 28 / 14.4) % 28).toFixed(2));
      c.style.setProperty("--f2", (-(k * 8 / 9.6) % 8).toFixed(2));
    }
  }, 1000 / 12);
})();
const _colorVar = new Map();
function colorVar(v, max = 0.06) {
  const clave = Math.round((v || 0) / max * 40) + "|" + max;   // 81 tonos bastan; se cachean
  let c = _colorVar.get(clave);
  if (!c) { c = _colorVarCalc(Math.round((v || 0) / max * 40) / 40 * max, max); _colorVar.set(clave, c); }
  return c;
}
function _colorVarCalc(v, max) {
  const t = Math.min(Math.abs(v || 0) / max, 1);
  return v >= 0 ? d3.interpolateRgb("#17241f", "#16c784")(0.15 + 0.85 * t) : d3.interpolateRgb("#2a191c", "#ef4444")(0.15 + 0.85 * t);
}

// ---------- gráficos (TradingView Lightweight Charts) ----------
const LW = LightweightCharts;
function crearGrafico(el, extra = {}) {
  const ch = LW.createChart(el, Object.assign({
    width: el.clientWidth, height: el.clientHeight,
    layout: { background: { type: "solid", color: "transparent" }, textColor: "#8a94a8", fontFamily: "Inter, Segoe UI, sans-serif" },
    grid: { vertLines: { color: "#161c29" }, horzLines: { color: "#161c29" } },
    rightPriceScale: { borderColor: "#232b3d" }, timeScale: { borderColor: "#232b3d" },
    crosshair: { mode: LW.CrosshairMode.Normal },
  }, extra));
  new ResizeObserver(() => ch.applyOptions({ width: el.clientWidth, height: el.clientHeight })).observe(el);
  return ch;
}
// update() falla si llega un punto más viejo que el último (nodo que se reincorpora): se ignora.
function upd(serie, punto) { try { serie.update(punto); } catch (e) { /* fuera de orden */ } }
function velasSerie(ch) {
  const v = ch.addCandlestickSeries({ upColor: "#16c784", downColor: "#ef4444", borderVisible: false, wickUpColor: "#16c784", wickDownColor: "#ef4444" });
  const vol = ch.addHistogramSeries({ priceFormat: { type: "volume" }, priceScaleId: "vol" });
  ch.priceScale("vol").applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
  return {
    async cargar(tk) {
      const velas = await (await fetch(`/api/velas/${encodeURIComponent(tk)}`)).json();
      v.setData(velas.map(({ time, open, high, low, close }) => ({ time, open, high, low, close })));
      vol.setData(velas.map((x) => ({ time: x.time, value: x.value, color: x.close >= x.open ? "#16c78455" : "#ef444455" })));
      ch.timeScale().fitContent();
    },
    nueva(x) {
      upd(v, { time: x.time, open: x.open, high: x.high, low: x.low, close: x.close });
      upd(vol, { time: x.time, value: x.value, color: x.close >= x.open ? "#16c78455" : "#ef444455" });
    },
  };
}

// ---------- datos en vivo ----------
const st = { glob: {}, nodos: {}, activos: {}, colombia: {}, mundo: [], politica: [], eventos: [], series_nodo: {},
             series_region: {}, regiones: {} };
function conectar({ snapshot, delta }) {
  const ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`);
  ws.onopen = () => document.querySelectorAll(".punto").forEach((p) => p.classList.add("ok"));
  ws.onclose = () => { document.querySelectorAll(".punto").forEach((p) => p.classList.remove("ok")); setTimeout(() => conectar({ snapshot, delta }), 1500); };
  ws.onmessage = (ev) => {
    const d = JSON.parse(ev.data);
    if (d.tipo === "snapshot") {
      Object.assign(st, { glob: d.global || {}, nodos: d.nodos || {}, activos: d.activos || {}, colombia: d.colombia || {},
        mundo: d.mundo || [], politica: d.politica || [], eventos: d.eventos || [], series_nodo: d.series_nodo || {},
        series_region: d.series_region || {}, regiones: d.regiones || {} });
      snapshot(st);
    } else {
      st.glob = d.global || st.glob; Object.assign(st.nodos, d.nodos); st.activos = d.activos; st.colombia = d.colombia;
      st.regiones = d.regiones || st.regiones;
      Object.entries(d.series_nodo || {}).forEach(([n, p]) => {
        const s = (st.series_nodo[n] = st.series_nodo[n] || []);
        s.push(p); if (s.length > 1200) s.splice(0, 400);   // sin tope crecía sin fin durante la presentación
      });
      Object.entries(d.series_region || {}).forEach(([c, p]) => {
        const s = (st.series_region[c] = st.series_region[c] || []);
        if (!s.length || s[s.length - 1].t !== p.t) s.push(p);
        if (s.length > 1200) s.splice(0, 400);
      });
      (d.mundo || []).forEach((m) => st.mundo.push(m));
      (d.politica || []).forEach((p) => st.politica.push(p));
      st.eventos.push(...(d.eventos || []));
      for (const k of ["mundo", "politica", "eventos"]) if (st[k].length > 900) st[k].splice(0, 300);
      delta(st, d);
    }
  };
}
const post = (url, body) => fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }).then((r) => r.json());

// ---------- navegación y encabezado ----------
function navegacion(activo) {
  const items = [["general", "/", "Panel general"], ...NODOS.map((n) => [n, `/nodo/${n}`, NOMBRE[n]])];
  return `<nav class="nav">${items.map(([k, href, t]) => `<a href="${href}" class="${k === activo ? "activo" : ""}"
    style="--c:${COLOR[k] || "#d7deea"}">${k === "general" ? "◆" : "●"} ${t}</a>`).join("")}</nav>`;
}
function relojHtml() {
  return `<span class="punto"></span><span class="fecha">—</span> <span class="tenue">tick</span> <b class="tick">0</b>`;
}
function actualizarReloj() {
  document.querySelectorAll(".fecha").forEach((e) => e.textContent = st.glob.fecha || "—");
  document.querySelectorAll(".tick").forEach((e) => e.textContent = st.glob.t ?? 0);
}

// ---------- tooltip ----------
const tip = document.createElement("div");
tip.className = "tip";
document.addEventListener("DOMContentLoaded", () => document.body.appendChild(tip));
function mostrarTip(ev, html) { tip.innerHTML = html; tip.style.display = "block"; moverTip(ev); }
function moverTip(ev) {
  const x = Math.min(ev.clientX + 14, innerWidth - tip.offsetWidth - 8);
  const y = Math.min(ev.clientY + 14, innerHeight - tip.offsetHeight - 8);
  tip.style.left = x + "px"; tip.style.top = y + "px";
}
function ocultarTip() { tip.style.display = "none"; }

// ---------- geografía ----------
let _geo = null;
function cargarGeo() {
  if (!_geo) {
    const j = (u) => fetch(u).then((r) => r.json());
    _geo = Promise.all([j("/static/geo/colombia-departamentos.json"), j("/static/geo/boyaca-municipios.json"),
                        j("/static/geo/mundo-110m.json"), j("/static/geo/lugares.json")])
      .then(([dep, boy, mundo, lugares]) => ({ dep, boy, lugares,
        paises: topojson.feature(mundo, mundo.objects.countries) }));
  }
  return _geo;
}
// Departamentos continentales (San Andrés distorsiona el encuadre).
const continental = (dep) => ({ type: "FeatureCollection", features: dep.features.filter((f) => f.properties.cod !== "88") });

// ---------- mapa de calor tipo "treemap" ----------
function treemap(el, activos, { agrupar = (a) => a.reg, etiquetaGrupo = (g) => g, alto } = {}) {
  const w = el.clientWidth, h = alto || el.clientHeight || 360;
  const grupos = d3.group(activos, agrupar);
  const raiz = d3.hierarchy({ children: [...grupos].map(([g, xs]) => ({ g, children: xs.map((a) => ({ a })) })) })
    .sum((d) => d.a ? Math.sqrt(Math.max(d.a.cap, 1)) : 0).sort((x, y) => y.value - x.value);
  d3.treemap().size([w, h]).paddingTop(18).paddingInner(2).paddingOuter(2).round(true)(raiz);
  const svg = d3.select(el).selectAll("svg").data([0]).join("svg").attr("width", w).attr("height", h);
  const grp = svg.selectAll("g.grupo").data(raiz.children || [], (d) => d.data.g).join((e) => {
    const g = e.append("g").attr("class", "grupo");
    g.append("rect").attr("class", "marco"); g.append("text").attr("class", "titulo-grupo");
    return g;
  });
  grp.select("rect.marco").attr("x", (d) => d.x0).attr("y", (d) => d.y0).attr("width", (d) => d.x1 - d.x0).attr("height", (d) => d.y1 - d.y0);
  grp.select("text.titulo-grupo").attr("x", (d) => d.x0 + 5).attr("y", (d) => d.y0 + 13).text((d) => etiquetaGrupo(d.data.g));
  const celdas = svg.selectAll("g.celda").data(raiz.leaves(), (d) => d.data.a.tk).join((e) => {
    const g = e.append("g").attr("class", "celda");
    g.append("rect"); g.append("text").attr("class", "tk"); g.append("text").attr("class", "vr");
    return g;
  });
  celdas.attr("transform", (d) => `translate(${d.x0},${d.y0})`)
    .on("mousemove", (ev, d) => mostrarTip(ev, `<b>${d.data.a.tk}</b><br>${SECTORES[d.data.a.sec] || d.data.a.sec} · ${d.data.a.reg}
      <br>Precio ${fmt(d.data.a.p, decimales(d.data.a))} ${d.data.a.mon}<br>Día <span class="${clase(d.data.a.var)}">${pct(d.data.a.var)}</span>
      · Total <span class="${clase(d.data.a.var_total)}">${pct(d.data.a.var_total, 1)}</span><br>Cap. ${corto(d.data.a.cap)}`))
    .on("mouseleave", ocultarTip);
  celdas.select("rect").attr("width", (d) => Math.max(0, d.x1 - d.x0)).attr("height", (d) => Math.max(0, d.y1 - d.y0))
    .attr("fill", (d) => colorVar(d.data.a.var, 0.03)).attr("rx", 3);
  celdas.select("text.tk").attr("x", 4).attr("y", 13).text((d) => (d.x1 - d.x0 > 46 && d.y1 - d.y0 > 16) ? d.data.a.tk.split(".")[1] : "");
  celdas.select("text.vr").attr("x", 4).attr("y", 26).text((d) => (d.x1 - d.x0 > 46 && d.y1 - d.y0 > 30) ? pct(d.data.a.var, 1) : "");
  return celdas;
}

// ---------- noticias ----------
function etiquetaEvento(t) { return { quiebra: "quiebra", nueva_empresa: "nueva", quiebra_personal: "insolvencia", nodo_caido: "caída", choque: "choque" }[t] || t; }
function htmlEventos(lista) {
  return lista.slice(-80).reverse().map((e) => `<li><span class="tag ${e.tipo}">${etiquetaEvento(e.tipo)}</span>
    <span class="tenue">t${e.t} · ${NOMBRE[e.nodo] || e.nodo}</span> ${e.texto}</li>`).join("");
}

// ---------- choques ----------
const CHOQUES = [
  ["crisis_financiera", "Crisis financiera", "Recorta el crédito y dispara la volatilidad"],
  ["pandemia", "Pandemia", "Cae el consumo y la productividad"],
  ["crisis_internacional", "Crisis internacional", "Baja la demanda externa y el petróleo"],
  ["boom_consumo", "Boom de consumo", "Los hogares gastan más"],
  ["inflacion", "Choque inflacionario", "Suben los precios"],
  ["subida_tasas", "BanRep sube tasas", "+puntos a la tasa de intervención"],
  ["bajada_tasas", "BanRep baja tasas", "−puntos a la tasa de intervención"],
  ["boom_petrolero", "Boom petrolero", "Sube el crudo y entran dólares"],
  ["guerra_comercial", "Guerra comercial", "EE. UU. y China suben aranceles"],
  ["fin_guerra_comercial", "Fin guerra comercial", "Aranceles vuelven a lo normal"],
];
function panelChoques(el, objetivoFijo) {
  el.innerHTML = `<div class="fila-form">
    ${objetivoFijo ? `<span class="tenue">Objetivo: <b style="color:${COLOR[objetivoFijo]}">${NOMBRE[objetivoFijo]}</b></span>` :
      `<label>Objetivo <select class="ch-obj"><option value="todos">Todos los nodos</option>${NODOS.map((n) => `<option value="${n}">${NOMBRE[n]}</option>`).join("")}</select></label>`}
    <label>Magnitud <input type="range" class="ch-mag" min="0.5" max="3" step="0.5" value="1"><b class="ch-mag-val">1</b></label>
    <label>Duración <input type="number" class="ch-dur" value="60" min="5" max="500"> ticks</label></div>
    <div class="botones">${CHOQUES.map(([k, n, d]) => `<button data-k="${k}" title="${d}"><b>${n}</b><small>${d}</small></button>`).join("")}</div>
    <div class="ch-resp tenue"></div>`;
  $(".ch-mag", el).oninput = (e) => $(".ch-mag-val", el).textContent = e.target.value;
  el.querySelectorAll("button").forEach((b) => b.onclick = async () => {
    const r = await post("/api/choque", { tipo: b.dataset.k, magnitud: +$(".ch-mag", el).value,
      objetivo: objetivoFijo || $(".ch-obj", el).value, duracion: +$(".ch-dur", el).value });
    $(".ch-resp", el).textContent = r.ok ? `Enviado: ${b.querySelector("b").textContent}. Se aplica en el próximo tick.` : r.error;
  });
}

// ---------- KPIs ----------
function kpiHtml(items) {
  return items.map(([e, v, s, c]) => `<div class="kpi"><div class="et">${e}</div><div class="val ${c || ""}">${v}</div><div class="sub">${s || ""}</div></div>`).join("");
}
