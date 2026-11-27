// Panel general: toda la red de un vistazo.
$("#nav").innerHTML = navegacion("general");
$("#reloj").innerHTML = relojHtml() + ` <span class="tenue" id="tps"></span>`;
const ui = { sel: null, filtro: "todos", orden: ["cap", -1], busca: "" };

// ---------- gráficos ----------
const gVelas = crearGrafico($("#grafico-velas"));
const velas = velasSerie(gVelas);
const gInd = crearGrafico($("#grafico-indices"));
const sInd = {};
NODOS.forEach((n) => sInd[n] = gInd.addLineSeries({ color: COLOR[n], lineWidth: 2, title: NOMBRE[n], priceLineVisible: false }));
const gTrm = crearGrafico($("#grafico-trm"), { leftPriceScale: { visible: true, borderColor: "#232b3d" } });
const sTrm = gTrm.addLineSeries({ color: "#f5a524", lineWidth: 2, title: "TRM", priceLineVisible: false });
const sPet = gTrm.addLineSeries({ color: "#a78bfa", lineWidth: 1, title: "Petróleo", priceScaleId: "left", priceLineVisible: false });
const gTasa = crearGrafico($("#grafico-tasa"));
const sTasa = gTasa.addLineSeries({ color: "#3b82f6", lineWidth: 2, title: "Tasa BanRep", lineType: 1, priceLineVisible: false });
const sInfl = gTasa.addLineSeries({ color: "#ef4444", lineWidth: 2, title: "Inflación", priceLineVisible: false });
const sMeta = gTasa.addLineSeries({ color: "#8a94a855", lineWidth: 1, lineStyle: 2, title: "Meta 3%", priceLineVisible: false });

// ---------- mapa de la red ----------
const mapa = { listo: false };
cargarGeo().then((geo) => {
  const el = $("#mapa-red");
  const W = 1000, H = 560;
  const { base: svg, arriba } = capasMapa(el, W, H);
  const defs = svg.append("defs");
  const glow = defs.append("filter").attr("id", "brillo");
  glow.append("feGaussianBlur").attr("stdDeviation", 3).attr("result", "b");
  glow.append("feMerge").selectAll("feMergeNode").data(["b", "SourceGraphic"]).join("feMergeNode").attr("in", (d) => d);

  const col = continental(geo.dep);
  const pCol = d3.geoMercator().fitExtent([[30, 40], [440, 540]], col);
  const paises = { type: "FeatureCollection", features: geo.paises.features.filter((f) => f.id !== "010") };
  const pMun = d3.geoNaturalEarth1().fitExtent([[470, 70], [990, 520]], paises);
  const gMundo = svg.append("g");
  gMundo.append("path").attr("d", d3.geoPath(pMun)({ type: "Sphere" })).attr("class", "esfera");
  gMundo.append("path").attr("d", d3.geoPath(pMun)(d3.geoGraticule10())).attr("class", "reticula");
  const paisesSel = gMundo.selectAll("path.pais").data(paises.features).join("path").attr("class", "pais")
    .attr("d", d3.geoPath(pMun))
    .on("mousemove", (ev, f) => {
      const cod = Object.keys(ISO_NUM).find((k) => ISO_NUM[k] === f.id);
      const r = cod && st.regiones[cod];
      mostrarTip(ev, r ? `<b>${r.nombre}</b> · nodo internacional<br>Índice ${fmt(r.indice, 1)} (${pct(r.var20, 1)} en 20 días)
        <br>Inflación ${fmt(r.inflacion, 1)}% · tasa ${fmt(r.tasa, 2)}%<br>${r.empresas} empresas` : (f.properties.name || ""));
    }).on("mouseleave", ocultarTip).on("click", () => location.href = "/nodo/internacional");
  const gCol = svg.append("g");
  const deps = gCol.selectAll("path.dep").data(col.features).join("path").attr("class", "dep").attr("d", d3.geoPath(pCol))
    .on("mousemove", (ev, f) => {
      const cod = COD_DEP[f.properties.cod]; const r = cod && st.regiones[cod];
      mostrarTip(ev, `<b>${f.properties.nombre}</b><br>Censo 2018: ${fmt(f.properties.pob2018, 0)} hab.` + (r ? `<br>Índice ${fmt(r.indice, 1)}
        (${pct(r.var20, 1)})<br>Inflación ${fmt(r.inflacion, 1)}% · desempleo ${fmt(r.desempleo, 1)}%<br>${r.empresas} empresas` : "<br><span class='tenue'>no simulado</span>"));
    }).on("mouseleave", ocultarTip).on("click", (ev, f) => COD_DEP[f.properties.cod] && (location.href = "/nodo/departamentos"));

  const ciudades = geo.lugares.ciudades;
  const pt = (c) => pCol([c.lon, c.lat]);
  const gMundoF = arriba.append("g");   // conexiones Colombia → mundo (animadas: capa de arriba)
  const gCiud = arriba.append("g");
  const ciudSel = gCiud.selectAll("g.ciudad").data(Object.entries(ciudades)).join("g").attr("class", "ciudad")
    .attr("transform", ([, c]) => `translate(${pt(c)})`)
    .on("mousemove", (ev, [cod, c]) => { const r = st.regiones[cod]; mostrarTip(ev, `<b>${c.nombre}</b><br>Censo 2018: ${fmt(c.pob2018, 0)} hab.`
      + (r ? `<br>Índice ${fmt(r.indice, 1)} (${pct(r.var20, 1)})<br>Desempleo ${fmt(r.desempleo, 1)}% · ${r.empresas} empresas` : "")); })
    .on("mouseleave", ocultarTip).on("click", ([cod]) => location.href = cod === "TUN" ? "/nodo/tunja" : "/nodo/capitales");
  ciudSel.append("circle").attr("class", "pulso").attr("r", 8);
  ciudSel.append("circle").attr("class", "nucleo").attr("r", 4);
  ciudSel.append("text").attr("class", "rotulo").attr("x", 7).attr("y", -6).text(([, c]) => c.nombre);
  ciudSel.classed("tunja", ([cod]) => cod === "TUN");

  // Nodos como insignias sobre su geografía.
  const bog = pt(ciudades.BOG), tun = pt(ciudades.TUN), ant = pCol([-75.5, 7.0]), sur = pCol([-72.6, 0.9]);
  const anclas = {
    tunja: [tun[0] + 70, tun[1] - 34], capitales: [bog[0] - 150, bog[1] + 26], departamentos: [ant[0] - 110, ant[1] - 70],
    colombia: [sur[0], sur[1]], internacional: [730, 36],
  };
  Object.values(anclas).forEach((a) => { a[0] = Math.max(82, Math.min(918, a[0])); a[1] = Math.max(26, Math.min(534, a[1])); });
  const origenes = { tunja: tun, capitales: bog, departamentos: ant, colombia: pCol([-73.5, 3.5]), internacional: [730, 52] };
  const gFlujos = arriba.append("g");
  const gNodos = arriba.append("g");
  const ins = gNodos.selectAll("g.insignia").data(NODOS).join("g").attr("class", "insignia").style("--c", (n) => COLOR[n])
    .attr("transform", (n) => `translate(${anclas[n]})`).style("cursor", "pointer").on("click", (ev, n) => location.href = `/nodo/${n}`);
  ins.append("line").attr("class", "guia").attr("x1", 0).attr("y1", 0)
    .attr("x2", (n) => origenes[n][0] - anclas[n][0]).attr("y2", (n) => origenes[n][1] - anclas[n][1]).attr("stroke", (n) => COLOR[n]);
  ins.append("rect").attr("x", -78).attr("y", -17).attr("width", 156).attr("height", 34).attr("rx", 9)
    .attr("stroke", (n) => COLOR[n]);
  ins.append("text").attr("class", "n1").attr("y", -2).attr("text-anchor", "middle").text((n) => NOMBRE[n].toUpperCase()).attr("fill", (n) => COLOR[n]);
  ins.append("text").attr("class", "n2").attr("y", 11).attr("text-anchor", "middle");

  // Conexiones desde Colombia a los países simulados.
  const centro = (cod) => { const f = paises.features.find((p) => p.id === ISO_NUM[cod]); return f ? pMun(d3.geoCentroid(f)) : null; };
  const colMundo = centro("COL");
  const enlaces = Object.keys(ISO2).map((k) => ({ k, p: centro(k) })).filter((x) => x.p);
  gMundoF.selectAll("path").data(enlaces).join("path").attr("class", "enlace-mundo")
    .attr("d", (e) => { const [x1, y1] = colMundo, [x2, y2] = e.p; const mx = (x1 + x2) / 2, my = Math.min(y1, y2) - 40;
      return `M${x1},${y1} Q${mx},${my} ${x2},${y2}`; });
  gMundoF.append("circle").attr("cx", colMundo[0]).attr("cy", colMundo[1]).attr("r", 3.5).attr("class", "col-mundo");

  Object.assign(mapa, { listo: true, deps, paisesSel, ciudSel, ins, gFlujos, anclas });
  pintarMapa();
});

function pintarMapa() {
  if (!mapa.listo) return;
  const R = st.regiones;
  mapa.deps.attr("fill", (f) => { const c = COD_DEP[f.properties.cod]; return c && R[c] ? colorVar(R[c].var20) : "#131925"; })
    .classed("simulado", (f) => !!COD_DEP[f.properties.cod]);
  mapa.paisesSel.attr("fill", (f) => {
    if (f.id === ISO_NUM.COL) return "#3a2a12";
    const c = Object.keys(ISO_NUM).find((k) => ISO_NUM[k] === f.id);
    return c && R[c] ? colorVar(R[c].var20) : "#121722";
  }).classed("simulado", (f) => Object.values(ISO_NUM).includes(f.id));
  const caps = {};
  Object.values(st.activos).forEach((a) => caps[a.reg] = (caps[a.reg] || 0) + a.cap);
  const maxCap = Math.max(...Object.keys(st.regiones).filter((k) => k.length === 3).map((k) => caps[k] || 0), 1);
  mapa.ciudSel.select("circle.nucleo").attr("r", ([cod]) => 3 + 9 * Math.sqrt((caps[cod] || 0) / maxCap))
    .attr("fill", ([cod]) => cod === "TUN" ? COLOR.tunja : R[cod] ? colorVar(R[cod].var20, 0.05) : "#3b82f6");
  const g = st.glob.nodos || {};
  mapa.ins.classed("caido", (n) => g[n] && !g[n].vivo);
  mapa.ins.select("text.n2").text((n) => {
    const s = g[n] || {}, e = st.nodos[n];
    if (!s.vivo) return "CAÍDO";
    return `${fmt(s.red_ms, 1)} ms · ${e ? e.ind.empresas : "—"} emp · ${e ? pct(e.ind.indice / 1000 - 1, 1) : ""}`;
  });
  // Flujos de órdenes entre nodos (ida y vuelta sumadas).
  const flujos = [];
  NODOS.forEach((a) => Object.entries((st.nodos[a] || {}).flujos || {}).forEach(([b, n]) => n && flujos.push({ a, b, n })));
  const max = Math.max(...flujos.map((f) => f.n), 1);
  mapa.gFlujos.selectAll("path").data(flujos, (f) => f.a + ">" + f.b).join((e) => e.append("path").attr("class", "flujo"))
    .attr("d", (f) => { const [x1, y1] = mapa.anclas[f.a], [x2, y2] = mapa.anclas[f.b];
      const dx = x2 - x1, dy = y2 - y1, k = 0.25; return `M${x1},${y1} Q${(x1 + x2) / 2 - dy * k},${(y1 + y2) / 2 + dx * k} ${x2},${y2}`; })
    .attr("stroke", (f) => COLOR[f.a]).attr("stroke-width", (f) => 0.8 + 3 * Math.sqrt(f.n / max)).attr("opacity", (f) => 0.35 + 0.5 * Math.sqrt(f.n / max))
    .attr("opacity", (f) => 0.35 + 0.6 * (f.n / max));
}

// ---------- paneles ----------
function kpis() {
  const m = st.mundo[st.mundo.length - 1] || {}, m0 = st.mundo[Math.max(0, st.mundo.length - 21)] || m;
  const p = st.politica[st.politica.length - 1] || {};
  const c = st.colombia || {};
  const agentes = Object.values(st.nodos).reduce((a, n) => a + (n.ind ? n.ind.agentes : 0), 0);
  const int = st.nodos.internacional;
  $("#kpis").innerHTML = kpiHtml([
    ["TRM (COP/USD)", fmt(m.trm), `${pct(m.trm / m0.trm - 1, 1)} en 20 días`],
    ["Petróleo (USD)", fmt(m.petroleo), `${pct(m.petroleo / m0.petroleo - 1, 1)} en 20 días`],
    ["Tasa BanRep", fmt(p.tasa) + "%", p.junta ? "junta este mes" : "intervención"],
    ["Inflación COL", fmt(c.inflacion) + "%", "anual · meta 3%", c.inflacion > 4 ? "baja" : ""],
    ["Desempleo COL", fmt(c.desempleo, 1) + "%", "fuerza laboral"],
    ["Índice COL", fmt(c.indice, 1), "base 1000", clase((c.indice || 1000) - 1000)],
    ["Índice mundial", fmt(int && int.ind.indice, 1), "base 1000", clase(int ? int.ind.indice - 1000 : 0)],
    ["Empresas COL", fmt(c.empresas, 0), `${c.quiebras ?? 0} quiebras · ${c.nuevas ?? 0} nuevas`],
    ["Agentes", fmt(agentes, 0), `${Object.values(st.glob.nodos || {}).filter((n) => n.vivo).length}/5 nodos en línea`],
  ]);
}

function nodos() {
  const g = st.glob.nodos || {};
  $("#nodos").innerHTML = NODOS.map((n) => {
    const s = g[n] || {}, e = st.nodos[n];
    return `<a class="nodo ${s.vivo ? "" : "caido"}" href="/nodo/${n}" style="--c:${COLOR[n]}">
      <b>${NOMBRE[n]} <span class="estado">${s.vivo ? "EN LÍNEA" : "CAÍDO"}</span></b>
      <div class="m">red ${fmt(s.red_ms, 1)} ms · cómputo ${fmt(s.ms, 1)} ms</div>
      <div class="m">${fmt(s.agentes, 0)} agentes · ${e ? e.ind.empresas : "—"} empresas</div>
      <div class="m">órdenes remotas ↑${e ? e.remotas_enviadas : 0} ↓${e ? e.remotas_recibidas : 0}</div>
      <div class="m">${e ? "infl " + fmt(e.ind.inflacion) + "% · desemp " + fmt(e.ind.desempleo, 1) + "%" : ""}</div></a>`;
  }).join("");
  actualizarReloj();
  $("#tps").textContent = st.glob.ticks_por_s ? `${fmt(st.glob.ticks_por_s, 2)} ticks/s` : "";
  $("#btn-pausa").textContent = st.glob.pausado ? "Reanudar" : "Pausar";
}

function pestanas() {
  const ops = ["todos", ...NODOS];
  $("#pestanas").innerHTML = ops.map((o) => `<button data-f="${o}" class="${ui.filtro === o ? "activa" : ""}">${o === "todos" ? "Todos" : NOMBRE[o]}</button>`).join("");
  $("#pestanas").querySelectorAll("button").forEach((b) => b.onclick = () => { ui.filtro = b.dataset.f; pestanas(); tabla(); });
}

function tabla() {
  let filas = Object.values(st.activos);
  if (ui.filtro !== "todos") filas = filas.filter((a) => a.nodo === ui.filtro);
  if (ui.busca) { const q = ui.busca.toLowerCase(); filas = filas.filter((a) => (a.tk + a.reg + a.sec + (SECTORES[a.sec] || "")).toLowerCase().includes(q)); }
  const [k, dir] = ui.orden;
  filas.sort((a, b) => (a[k] > b[k] ? 1 : a[k] < b[k] ? -1 : 0) * dir);
  const filaHtml = (a) => `<tr data-tk="${a.tk}" class="${a.tk === ui.sel ? "sel" : ""}">
    <td><span style="color:${COLOR[a.nodo]}">●</span> ${a.tk}</td><td class="num">${fmt(a.p, decimales(a))}</td>
    <td class="num ${clase(a.var)}">${pct(a.var)}</td><td class="num ${clase(a.var_total)}">${pct(a.var_total, 1)}</td>
    <td class="num">${corto(a.v)}</td></tr>`;
  const html = filas.slice(0, 300).map(filaHtml).join("");
  const tb = $("#tabla-activos tbody");
  if (html !== tb._html) { tb.innerHTML = html; tb._html = html; }   // no tocar el DOM si nada cambió
}
$("#tabla-activos tbody").onclick = (ev) => { const tr = ev.target.closest("tr"); if (tr) seleccionar(tr.dataset.tk); };

function cinta() {
  const top = Object.values(st.activos).sort((a, b) => b.cap - a.cap).slice(0, 30);
  const html = top.map((a) => `<span><i style="color:${COLOR[a.nodo]}">●</i> ${a.tk} <b>${fmt(a.p, decimales(a))}</b> <span class="${clase(a.var)}">${pct(a.var)}</span></span>`).join("");
  $("#cinta-contenido").innerHTML = html + html;
}

function encabezadoSel() {
  const a = st.activos[ui.sel];
  if (!a) { if (ui.sel) $("#sel-info").textContent = "Empresa en quiebra: ya no cotiza"; return; }
  $("#sel-ticker").textContent = a.tk;
  $("#sel-info").textContent = `${NOMBRE[a.nodo]} · ${a.reg} · ${SECTORES[a.sec] || a.sec} · ${a.mon} · cap ${corto(a.cap)}`;
  $("#sel-precio").textContent = fmt(a.p, decimales(a));
  $("#sel-var").textContent = pct(a.var);
  $("#sel-var").className = "var " + clase(a.var);
}

async function seleccionar(tk) { ui.sel = tk; await velas.cargar(tk); encabezadoSel(); tabla(); }

let ultimoTreemap = 0;
function pintarTreemap(forzar) {
  if (!forzar && Date.now() - ultimoTreemap < 2000) return;
  ultimoTreemap = Date.now();
  treemap($("#treemap"), Object.values(st.activos), { agrupar: (a) => a.nodo, etiquetaGrupo: (n) => NOMBRE[n].toUpperCase(), alto: 380 })
    .on("click", (ev, d) => seleccionar(d.data.a.tk));
}

// ---------- datos ----------
// Lo caro (tablas, mapa, treemap) se pinta como mucho 1 vez por segundo, aunque la simulación vaya a máxima velocidad.
let hayEventos = false, ultimaCinta = 0;
const pintarPaneles = limitar(() => {
  if (hayEventos) { $("#eventos").innerHTML = htmlEventos(st.eventos); hayEventos = false; }
  kpis(); nodos(); tabla(); encabezadoSel(); pintarMapa(); pintarTreemap();
  if (Date.now() - ultimaCinta > 8000) { cinta(); ultimaCinta = Date.now(); }
}, 1000);
conectar({
  snapshot(s) {
    Object.entries(s.series_nodo).forEach(([n, pts]) => sInd[n] && sInd[n].setData(pts.map((p) => ({ time: p.time, value: p.indice }))));
    sTrm.setData(s.mundo.map((m) => ({ time: m.time, value: m.trm })));
    sPet.setData(s.mundo.map((m) => ({ time: m.time, value: m.petroleo })));
    sTasa.setData(s.politica.map((p) => ({ time: p.time, value: p.tasa })));
    sInfl.setData(s.politica.filter((p) => p.inflacion != null).map((p) => ({ time: p.time, value: p.inflacion })));
    sMeta.setData(s.politica.map((p) => ({ time: p.time, value: 3 })));
    $("#eventos").innerHTML = htmlEventos(s.eventos);
    if (!ui.sel) { const top = Object.values(s.activos).sort((a, b) => b.cap - a.cap)[0]; if (top) seleccionar(top.tk); }
    kpis(); nodos(); tabla(); cinta(); pintarMapa(); pintarTreemap(true);
  },
  delta(s, d) {
    Object.entries(d.series_nodo || {}).forEach(([n, p]) => sInd[n] && upd(sInd[n], { time: p.time, value: p.indice }));
    (d.mundo || []).forEach((m) => { upd(sTrm, { time: m.time, value: m.trm }); upd(sPet, { time: m.time, value: m.petroleo }); });
    (d.politica || []).forEach((p) => { upd(sTasa, { time: p.time, value: p.tasa }); upd(sMeta, { time: p.time, value: 3 });
      if (p.inflacion != null) upd(sInfl, { time: p.time, value: p.inflacion }); });
    const v = ui.sel && d.velas[ui.sel];
    if (v) velas.nueva(v);
    if (d.eventos && d.eventos.length) hayEventos = true;
    pintarPaneles();
  },
});

// ---------- controles ----------
$("#btn-pausa").onclick = () => post("/api/control", { accion: "pausa", valor: !st.glob.pausado });
$("#velocidad").onchange = (e) => post("/api/control", { accion: "velocidad", valor: e.target.value });
$("#buscar").oninput = (e) => { ui.busca = e.target.value; tabla(); };
document.querySelectorAll("#tabla-activos th").forEach((th) => th.onclick = () => {
  const k = th.dataset.k; ui.orden = [k, ui.orden[0] === k ? -ui.orden[1] : -1]; tabla();
});
panelChoques($("#choques"));
pestanas();
