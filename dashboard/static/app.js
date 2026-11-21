// Dashboard en tiempo real de la bolsa distribuida.
const $ = (s) => document.querySelector(s);
const NODOS = ["tunja", "capitales", "departamentos", "colombia", "internacional"];
const NOMBRE = { coordinador: "Reloj global", tunja: "Tunja", capitales: "Capitales", departamentos: "Departamentos", colombia: "Colombia", internacional: "Internacional" };
const COLOR = { tunja: "#f5a524", capitales: "#3b82f6", departamentos: "#16c784", colombia: "#ea3943", internacional: "#8b5cf6" };
const CHOQUES = [
  ["crisis_financiera", "Crisis financiera"], ["pandemia", "Pandemia"], ["crisis_internacional", "Crisis internacional"],
  ["boom_consumo", "Boom de consumo"], ["inflacion", "Choque inflacionario"], ["subida_tasas", "BanRep sube tasas"],
  ["bajada_tasas", "BanRep baja tasas"], ["boom_petrolero", "Boom petrolero"], ["guerra_comercial", "Guerra comercial"],
  ["fin_guerra_comercial", "Fin guerra comercial"],
];

const st = { activos: {}, nodos: {}, glob: {}, sel: null, filtro: "todos", orden: ["cap", -1], busca: "", colombia: {},
             politica: [], mundo: [] };

// ---------- formato ----------
const fmt = (x, d = 2) => (x == null || isNaN(x)) ? "—" : Number(x).toLocaleString("es-CO", { minimumFractionDigits: d, maximumFractionDigits: d });
const pct = (x, d = 2) => (x == null || isNaN(x)) ? "—" : (x >= 0 ? "+" : "") + (100 * x).toFixed(d) + "%";
const clase = (x) => x > 0 ? "sube" : x < 0 ? "baja" : "";
const corto = (x) => { const a = Math.abs(x); return a >= 1e12 ? fmt(x / 1e12, 1) + "B" : a >= 1e9 ? fmt(x / 1e9, 1) + "MM" : a >= 1e6 ? fmt(x / 1e6, 1) + "M" : a >= 1e3 ? fmt(x / 1e3, 1) + "k" : fmt(x, 0); };

// ---------- gráficos ----------
const LW = LightweightCharts;
const baseOpts = (el) => ({
  width: el.clientWidth, height: el.clientHeight,
  layout: { background: { type: "solid", color: "transparent" }, textColor: "#7c8699", fontFamily: "Segoe UI, sans-serif" },
  grid: { vertLines: { color: "#1a2130" }, horzLines: { color: "#1a2130" } },
  rightPriceScale: { borderColor: "#232b3d" }, timeScale: { borderColor: "#232b3d", timeVisible: false },
  crosshair: { mode: LW.CrosshairMode.Normal },
});
function crear(id) {
  const el = document.getElementById(id);
  const ch = LW.createChart(el, baseOpts(el));
  new ResizeObserver(() => ch.applyOptions({ width: el.clientWidth, height: el.clientHeight })).observe(el);
  return ch;
}
const gVelas = crear("grafico-velas");
const sVelas = gVelas.addCandlestickSeries({ upColor: "#16c784", downColor: "#ea3943", borderVisible: false, wickUpColor: "#16c784", wickDownColor: "#ea3943" });
const sVol = gVelas.addHistogramSeries({ priceFormat: { type: "volume" }, priceScaleId: "vol", color: "#2b3550" });
gVelas.priceScale("vol").applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
const gInd = crear("grafico-indices");
const sInd = {};
NODOS.forEach((n) => sInd[n] = gInd.addLineSeries({ color: COLOR[n], lineWidth: 2, title: NOMBRE[n], priceLineVisible: false }));
const gTrm = crear("grafico-trm");
const sTrm = gTrm.addLineSeries({ color: "#f5a524", lineWidth: 2, title: "TRM", priceLineVisible: false });
const sPet = gTrm.addLineSeries({ color: "#8b5cf6", lineWidth: 1, title: "Petróleo", priceScaleId: "left", priceLineVisible: false });
gTrm.applyOptions({ leftPriceScale: { visible: true, borderColor: "#232b3d" } });
const gTasa = crear("grafico-tasa");
const sTasa = gTasa.addLineSeries({ color: "#3b82f6", lineWidth: 2, title: "Tasa BanRep", lineType: 1, priceLineVisible: false });
const sInfl = gTasa.addLineSeries({ color: "#ea3943", lineWidth: 2, title: "Inflación", priceLineVisible: false });

// ---------- render ----------
function kpis() {
  const m = st.mundo[st.mundo.length - 1] || {};
  const p = st.politica[st.politica.length - 1] || {};
  const c = st.colombia || {};
  const agentes = Object.values(st.nodos).reduce((a, n) => a + (n.ind ? n.ind.agentes : 0), 0);
  const int = st.nodos.internacional;
  const items = [
    ["TRM (COP/USD)", fmt(m.trm), ""], ["Petróleo (USD)", fmt(m.petroleo), ""],
    ["Tasa BanRep", fmt(p.tasa) + "%", p.junta ? "junta este mes" : ""], ["Inflación COL", fmt(c.inflacion) + "%", "anual"],
    ["Desempleo COL", fmt(c.desempleo, 1) + "%", ""], ["Índice COL", fmt(c.indice, 1), "base 1000"],
    ["Índice mundial", fmt(int && int.ind.indice, 1), "base 1000"],
    ["Empresas COL", fmt(c.empresas, 0), `${c.quiebras ?? 0} quiebras · ${c.nuevas ?? 0} nuevas`],
    ["Agentes", fmt(agentes, 0), `${Object.keys(st.nodos).length} nodos`],
  ];
  $("#kpis").innerHTML = items.map(([e, v, s]) => `<div class="kpi"><div class="et">${e}</div><div class="val">${v}</div><div class="sub tenue">${s}</div></div>`).join("");
}

function nodos() {
  const g = st.glob.nodos || {};
  $("#nodos").innerHTML = NODOS.map((n) => {
    const s = g[n] || {}; const e = st.nodos[n];
    const vivo = s.vivo;
    return `<div class="nodo ${vivo ? "" : "caido"}" style="border-left-color:${vivo ? COLOR[n] : ""}">
      <b>${NOMBRE[n]} ${vivo ? "" : "· CAÍDO"}</b>
      <div class="m">red ${fmt(s.red_ms, 1)} ms · cómputo ${fmt(s.ms, 1)} ms</div>
      <div class="m">${fmt(s.agentes, 0)} agentes · ${e ? e.ind.empresas : "—"} empresas</div>
      <div class="m">órdenes remotas ↑${e ? e.remotas_enviadas : 0} ↓${e ? e.remotas_recibidas : 0}</div>
      <div class="m">${e ? "infl " + fmt(e.ind.inflacion) + "% · desemp " + fmt(e.ind.desempleo, 1) + "%" : ""}</div></div>`;
  }).join("");
  $("#tick").textContent = st.glob.t ?? 0;
  $("#fecha").textContent = st.glob.fecha || "—";
  $("#tps").textContent = st.glob.ticks_por_s ? `${fmt(st.glob.ticks_por_s, 2)} ticks/s` : "";
  $("#btn-pausa").textContent = st.glob.pausado ? "Reanudar" : "Pausar";
}

function pestanas() {
  const ops = ["todos", ...NODOS];
  $("#pestanas").innerHTML = ops.map((o) => `<button data-f="${o}" class="${st.filtro === o ? "activa" : ""}">${o === "todos" ? "Todos" : NOMBRE[o]}</button>`).join("");
  $("#pestanas").querySelectorAll("button").forEach((b) => b.onclick = () => { st.filtro = b.dataset.f; pestanas(); tabla(); });
}

function tabla() {
  let filas = Object.values(st.activos);
  if (st.filtro !== "todos") filas = filas.filter((a) => a.nodo === st.filtro);
  if (st.busca) { const q = st.busca.toLowerCase(); filas = filas.filter((a) => (a.tk + a.reg + a.sec).toLowerCase().includes(q)); }
  const [k, dir] = st.orden;
  filas.sort((a, b) => (a[k] > b[k] ? 1 : a[k] < b[k] ? -1 : 0) * dir);
  $("#tabla-activos tbody").innerHTML = filas.slice(0, 300).map((a) => `<tr data-tk="${a.tk}" class="${a.tk === st.sel ? "sel" : ""}">
    <td><span style="color:${COLOR[a.nodo]}">●</span> ${a.tk}</td><td class="num">${fmt(a.p, a.mon === "USD" ? 2 : 1)}</td>
    <td class="num ${clase(a.var)}">${pct(a.var)}</td><td class="num ${clase(a.var_total)}">${pct(a.var_total, 1)}</td>
    <td class="num">${corto(a.v)}</td></tr>`).join("");
  $("#tabla-activos tbody").querySelectorAll("tr").forEach((tr) => tr.onclick = () => seleccionar(tr.dataset.tk));
}

function cinta() {
  const top = Object.values(st.activos).sort((a, b) => b.cap - a.cap).slice(0, 30);
  const html = top.map((a) => `<span>${a.tk} <b>${fmt(a.p, a.mon === "USD" ? 2 : 1)}</b> <span class="${clase(a.var)}">${pct(a.var)}</span></span>`).join("");
  $("#cinta-contenido").innerHTML = html + html;
}

function mapa(regiones) {
  const orden = Object.entries(regiones).sort((a, b) => NODOS.indexOf(a[1].nodo) - NODOS.indexOf(b[1].nodo));
  $("#mapa").innerHTML = orden.map(([cod, r]) => {
    const v = r.var20 || 0; const a = Math.min(Math.abs(v) / 0.1, 1);
    const bg = v >= 0 ? `rgba(22,199,132,${0.15 + 0.6 * a})` : `rgba(234,57,67,${0.15 + 0.6 * a})`;
    return `<div class="region" style="background:${bg}" title="${r.nombre} (${NOMBRE[r.nodo]})">
      <b>${cod}</b><div>${r.nombre}</div><div class="m">${pct(v, 1)} · infl ${fmt(r.inflacion, 1)}%</div>
      <div class="m">desemp ${fmt(r.desempleo, 1)}% · ${r.empresas} emp.</div></div>`;
  }).join("");
}

function eventos(lista, nuevos = true) {
  const ul = $("#eventos");
  const html = lista.slice(-60).reverse().map((e) => `<li><span class="tag ${e.tipo}">${e.tipo.replace("_", " ")}</span>
    <span class="tenue">t${e.t} · ${NOMBRE[e.nodo] || e.nodo}</span> ${e.texto}</li>`).join("");
  ul.innerHTML = nuevos ? html + ul.innerHTML : html;
  while (ul.children.length > 120) ul.lastChild.remove();
}

function encabezadoSel() {
  const a = st.activos[st.sel];
  if (!a) return;
  $("#sel-ticker").textContent = a.tk;
  $("#sel-info").textContent = `${NOMBRE[a.nodo]} · ${a.reg} · sector ${a.sec} · ${a.mon} · cap ${corto(a.cap)}`;
  $("#sel-precio").textContent = fmt(a.p, a.mon === "USD" ? 2 : 1);
  $("#sel-var").textContent = pct(a.var);
  $("#sel-var").className = "var " + clase(a.var);
}

async function seleccionar(tk) {
  st.sel = tk;
  const r = await fetch(`/api/velas/${encodeURIComponent(tk)}`);
  const velas = await r.json();
  sVelas.setData(velas.map(({ time, open, high, low, close }) => ({ time, open, high, low, close })));
  sVol.setData(velas.map((v) => ({ time: v.time, value: v.value, color: v.close >= v.open ? "#16c78455" : "#ea394355" })));
  gVelas.timeScale().fitContent();
  encabezadoSel(); tabla();
}

// update() falla si llega un punto más viejo que el último (p. ej. un nodo que se reincorpora): se ignora.
function upd(serie, punto) { try { serie.update(punto); } catch (e) { /* punto fuera de orden */ } }

function serieNodo(n, puntos) { sInd[n].setData(puntos.map((p) => ({ time: p.time, value: p.indice }))); }

// ---------- datos ----------
function aplicarSnapshot(d) {
  st.glob = d.global || {}; st.nodos = d.nodos || {}; st.activos = d.activos || {}; st.colombia = d.colombia || {};
  st.mundo = d.mundo || []; st.politica = d.politica || [];
  Object.entries(d.series_nodo || {}).forEach(([n, pts]) => sInd[n] && serieNodo(n, pts));
  sTrm.setData(st.mundo.map((m) => ({ time: m.time, value: m.trm })));
  sPet.setData(st.mundo.map((m) => ({ time: m.time, value: m.petroleo })));
  sTasa.setData(st.politica.map((p) => ({ time: p.time, value: p.tasa })));
  sInfl.setData(st.politica.filter((p) => p.inflacion != null).map((p) => ({ time: p.time, value: p.inflacion })));
  eventos(d.eventos || [], false);
  mapa(d.regiones || {});
  if (!st.sel) { const top = Object.values(st.activos).sort((a, b) => b.cap - a.cap)[0]; if (top) seleccionar(top.tk); }
  kpis(); nodos(); tabla(); cinta();
}

function aplicarDelta(d) {
  st.glob = d.global || st.glob; Object.assign(st.nodos, d.nodos); st.activos = d.activos; st.colombia = d.colombia;
  Object.entries(d.series_nodo || {}).forEach(([n, p]) => sInd[n] && upd(sInd[n], { time: p.time, value: p.indice }));
  (d.mundo || []).forEach((m) => { st.mundo.push(m); upd(sTrm, { time: m.time, value: m.trm }); upd(sPet, { time: m.time, value: m.petroleo }); });
  (d.politica || []).forEach((p) => { st.politica.push(p); upd(sTasa, { time: p.time, value: p.tasa }); if (p.inflacion != null) upd(sInfl, { time: p.time, value: p.inflacion }); });
  if (st.mundo.length > 800) st.mundo.splice(0, 200);
  if (st.politica.length > 800) st.politica.splice(0, 200);
  const v = st.sel && d.velas[st.sel];
  if (v) { upd(sVelas, { time: v.time, open: v.open, high: v.high, low: v.low, close: v.close });
           upd(sVol, { time: v.time, value: v.value, color: v.close >= v.open ? "#16c78455" : "#ea394355" }); }
  if (st.sel && !st.activos[st.sel]) $("#sel-info").textContent = "Empresa en quiebra: ya no cotiza";
  if (d.eventos && d.eventos.length) eventos(d.eventos);
  mapa(d.regiones || {});
  kpis(); nodos(); tabla(); encabezadoSel();
  if ((st.glob.t || 0) % 10 === 0) cinta();
}

function conectar() {
  const ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`);
  ws.onopen = () => $("#estado-conexion").classList.add("ok");
  ws.onclose = () => { $("#estado-conexion").classList.remove("ok"); setTimeout(conectar, 1500); };
  ws.onmessage = (ev) => { const d = JSON.parse(ev.data); d.tipo === "snapshot" ? aplicarSnapshot(d) : aplicarDelta(d); };
}

// ---------- controles ----------
const post = (url, body) => fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }).then((r) => r.json());
$("#btn-pausa").onclick = () => post("/api/control", { accion: "pausa", valor: !st.glob.pausado });
$("#velocidad").onchange = (e) => post("/api/control", { accion: "velocidad", valor: e.target.value });
$("#buscar").oninput = (e) => { st.busca = e.target.value; tabla(); };
document.querySelectorAll("#tabla-activos th").forEach((th) => th.onclick = () => {
  const k = th.dataset.k; st.orden = [k, st.orden[0] === k ? -st.orden[1] : -1]; tabla();
});
$("#choque-mag").oninput = (e) => $("#mag-val").textContent = e.target.value;
$("#botones-choque").innerHTML = CHOQUES.map(([k, n]) => `<button data-k="${k}">${n}</button>`).join("");
$("#botones-choque").querySelectorAll("button").forEach((b) => b.onclick = async () => {
  const r = await post("/api/choque", { tipo: b.dataset.k, magnitud: +$("#choque-mag").value,
    objetivo: $("#choque-objetivo").value, duracion: +$("#choque-dur").value });
  $("#choque-resp").textContent = r.ok ? `Choque enviado: ${b.textContent} (se aplica en el próximo tick en todos los nodos)` : r.error;
});

pestanas();
conectar();
