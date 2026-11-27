// Vista propia de cada nodo, con su geografía.
const NODO = location.pathname.split("/").filter(Boolean)[1] || "tunja";
const PERFIL = {
  tunja: {
    sobre: "Nodo local · PC 1", titulo: "Tunja", desc: "La capital de Boyacá como mercado propio: comercio, educación, construcción, salud, turismo, agro, transporte y alimentos. Sus empresas cotizan en su propia bolsa y sus inversionistas compran en el resto del país y del mundo.",
    mapa: "Tunja en Boyacá", mapaSub: "123 municipios (DANE, Censo 2018) · Tunja resaltada", regiones: "Ciudad",
    especial: "Sectores de Tunja", especialSub: "capitalización y variación por sector",
  },
  capitales: {
    sobre: "Nodo urbano · PC 2", titulo: "Ciudades capitales", desc: "Bogotá, Medellín, Cali, Barranquilla, Bucaramanga y Cartagena: los grandes mercados urbanos, con finanzas, tecnología, comercio, puertos y turismo.",
    mapa: "Las seis capitales", mapaSub: "burbuja = capitalización · color = variación del índice en 20 días", regiones: "Ciudades",
    especial: "Ranking de ciudades", especialSub: "índice, desempleo e inflación",
  },
  departamentos: {
    sobre: "Nodo regional · PC 3", titulo: "Departamentos", desc: "Ocho departamentos con su vocación productiva: agro, minería, petróleo, café, flores, azúcar, ganadería y puertos. Son los más expuestos al petróleo y a la demanda externa.",
    mapa: "Colombia por departamentos", mapaSub: "ocho departamentos simulados · color = variación del índice en 20 días", regiones: "Departamentos",
    especial: "Tendencia por departamento", especialSub: "índice regional (últimos ticks)",
  },
  colombia: {
    sobre: "Nodo nacional · PC 4", titulo: "Colombia", desc: "Las grandes empresas nacionales y el Banco de la República, que cada mes fija la tasa de intervención con una regla de Taylor a partir de la inflación y el desempleo que reportan los cuatro nodos colombianos.",
    mapa: "Colombia", mapaSub: "inflación por región reportada a la junta del Banco de la República", regiones: "Nivel nacional",
    especial: "Junta del Banco de la República", especialSub: "meta de inflación 3%",
  },
  internacional: {
    sobre: "Nodo global · PC principal", titulo: "Mercado internacional", desc: "Nueve economías con reglas propias (impuestos, aranceles a Colombia, topes a la inversión extranjera), el precio del petróleo y la TRM, que reacciona a las tasas, al crudo y a los flujos de capital que cruzan la red.",
    mapa: "El mundo", mapaSub: "color = variación del índice del país en 20 días · líneas = comercio con Colombia", regiones: "Países",
    especial: "Países y reglas", especialSub: "tasa, inflación y arancel a Colombia",
  },
}[NODO];
document.body.className = `tema-${NODO}`;
document.title = `${PERFIL.titulo} · Bolsa Distribuida`;
$("#nav").innerHTML = navegacion(NODO);
$("#reloj").innerHTML = relojHtml();
$("#marca-nodo").textContent = `Nodo ${NOMBRE[NODO]}`;
$("#h-sobre").textContent = PERFIL.sobre;
$("#h-titulo").textContent = PERFIL.titulo;
$("#h-desc").textContent = PERFIL.desc;
$("#mapa-titulo").textContent = PERFIL.mapa;
$("#mapa-sub").textContent = PERFIL.mapaSub;
$("#regiones-titulo").textContent = PERFIL.regiones;
$("#especial-titulo").textContent = PERFIL.especial;
$("#especial-sub").textContent = PERFIL.especialSub;
const ui = { sel: null, region: null, orden: ["cap", -1] };
const PALETA = ["#f5a524", "#3b82f6", "#16c784", "#ef4444", "#a78bfa", "#22d3ee", "#f472b6", "#facc15", "#94a3b8"];

// ---------- gráficos ----------
const gVelas = crearGrafico($("#grafico-velas"));
const velas = velasSerie(gVelas);
const gReg = crearGrafico($("#grafico-regiones"));
const sReg = {};
const gMac = crearGrafico($("#grafico-macro"));
const sInfl = gMac.addLineSeries({ color: "#ef4444", lineWidth: 2, title: "Inflación", priceLineVisible: false });
const sDes = gMac.addLineSeries({ color: "#22d3ee", lineWidth: 2, title: "Desempleo", priceLineVisible: false });

const misRegiones = () => Object.keys((st.nodos[NODO] || {}).regiones || {});
const misActivos = () => Object.values(st.activos).filter((a) => a.nodo === NODO);
function serieRegion(cod, i) {
  if (!sReg[cod]) sReg[cod] = gReg.addLineSeries({ color: PALETA[i % PALETA.length], lineWidth: 2, title: cod, priceLineVisible: false });
  return sReg[cod];
}

// ---------- héroe ----------
function heroe() {
  const e = st.nodos[NODO], s = (st.glob.nodos || {})[NODO] || {};
  if (!e) return;
  const i = e.ind;
  const pob = PERFIL.pob ? ` · ${PERFIL.pob}` : "";
  $("#h-chips").innerHTML = `<span class="chip ${s.vivo ? "ok" : "mal"}">${s.vivo ? "● EN LÍNEA" : "● CAÍDO"}</span>
    <span class="chip">red ${fmt(s.red_ms, 1)} ms</span><span class="chip">cómputo ${fmt(s.ms, 1)} ms/tick</span>
    <span class="chip">${e.moneda}</span><span class="chip">${fmt(i.agentes, 0)} agentes</span>${pob ? `<span class="chip">${PERFIL.pob}</span>` : ""}`;
  $("#kpis").innerHTML = kpiHtml([
    ["Índice", fmt(i.indice, 1), "base 1000", clase(i.indice - 1000)],
    ["Inflación", fmt(i.inflacion) + "%", "anual"],
    ["Desempleo", fmt(i.desempleo, 1) + "%", "fuerza laboral"],
    ["Tasa de interés", fmt(i.tasa) + "%", NODO === "internacional" ? "promedio países" : "BanRep"],
    ["Empresas", fmt(i.empresas, 0), `${i.quiebras} quiebras · ${i.nuevas} nuevas`],
    ["PIB diario", corto(i.pib), e.moneda],
    ["Desigualdad", fmt(i.gini, 3), "Gini de riqueza"],
    ["Crédito", corto(i.credito), e.moneda],
  ]);
}

// ---------- mapas por nodo ----------
const mapa = { listo: false, pintar() {} };
let GEO = null;
cargarGeo().then((geo) => {
  GEO = geo;
  const el = $("#mapa");
  const W = 1000, H = 520;
  const { base: svg, arriba } = capasMapa(el, W, H);   // geografía abajo, animaciones arriba
  const R = () => st.regiones;
  const col = continental(geo.dep);
  const ciudades = geo.lugares.ciudades;
  const tipDep = (f) => { const c = COD_DEP[f.properties.cod]; const r = c && R()[c];
    return `<b>${f.properties.nombre}</b><br>Censo 2018: ${fmt(f.properties.pob2018, 0)} hab.` + (r && r.nodo === NODO ? `<br>Índice ${fmt(r.indice, 1)}
      (${pct(r.var20, 1)})<br>Inflación ${fmt(r.inflacion, 1)}% · desempleo ${fmt(r.desempleo, 1)}%<br>${r.empresas} empresas` : ""); };

  if (NODO === "tunja") {
    const proj = d3.geoMercator().fitExtent([[20, 20], [620, 500]], geo.boy);
    const path = d3.geoPath(proj);
    const maxPob = d3.max(geo.boy.features, (f) => f.properties.pob2018);
    const esc = d3.scaleSqrt().domain([0, maxPob / 6]).range([0, 1]).clamp(true);
    const mun = svg.append("g").selectAll("path").data(geo.boy.features).join("path").attr("class", "muni").attr("d", path)
      .attr("fill", (f) => f.properties.cod === "15001" ? COLOR.tunja : d3.interpolateRgb("#151b28", "#4a3a1a")(esc(f.properties.pob2018)))
      .classed("destacado", (f) => f.properties.cod === "15001")
      .on("mousemove", (ev, f) => mostrarTip(ev, `<b>${f.properties.nombre}</b><br>Censo 2018: ${fmt(f.properties.pob2018, 0)} hab.`
        + (f.properties.cod === "15001" ? "<br>Nodo simulado" : ""))).on("mouseleave", ocultarTip);
    const tun = geo.boy.features.find((f) => f.properties.cod === "15001");
    const [cx, cy] = path.centroid(tun);
    arriba.append("circle").attr("cx", cx).attr("cy", cy).attr("r", 14).attr("class", "pulso-grande");
    svg.append("text").attr("x", cx + 18).attr("y", cy - 10).attr("class", "rotulo-grande").text("TUNJA");
    // Recuadro: Boyacá dentro de Colombia.
    const pc = d3.geoMercator().fitExtent([[700, 40], [980, 480]], col);
    const g2 = svg.append("g");
    g2.selectAll("path").data(col.features).join("path").attr("d", d3.geoPath(pc)).attr("class", "dep")
      .attr("fill", (f) => f.properties.cod === "15" ? "#4a3a1a" : "#131925");
    const t2 = pc([ciudades.TUN.lon, ciudades.TUN.lat]);
    g2.append("circle").attr("cx", t2[0]).attr("cy", t2[1]).attr("r", 4).attr("fill", COLOR.tunja);
    g2.append("text").attr("x", 700).attr("y", 30).attr("class", "rotulo").text("Boyacá en Colombia");
    PERFIL.pob = `${fmt(tun.properties.pob2018, 0)} hab. (Censo 2018)`;
    mapa.pintar = () => {
      const r = R().TUN; if (!r) return;
      mun.filter((f) => f.properties.cod === "15001").attr("fill", d3.interpolateRgb(COLOR.tunja, colorVar(r.var20))(0.35));
    };
  } else if (NODO === "capitales" || NODO === "departamentos" || NODO === "colombia") {
    const proj = d3.geoMercator().fitExtent([[40, 20], [600, 505]], col);
    const path = d3.geoPath(proj);
    const deps = svg.append("g").selectAll("path").data(col.features).join("path").attr("class", "dep").attr("d", path)
      .on("mousemove", (ev, f) => mostrarTip(ev, tipDep(f))).on("mouseleave", ocultarTip)
      .on("click", (ev, f) => { const c = COD_DEP[f.properties.cod]; if (NODO === "departamentos" && c) filtrarRegion(c); });
    const pt = (c) => proj([c.lon, c.lat]);
    let burb = null;
    if (NODO === "capitales" || NODO === "colombia") {
      const cods = NODO === "capitales" ? ["BOG", "MED", "CAL", "BAQ", "BUC", "CTG"] : ["BOG"];
      burb = arriba.append("g").selectAll("g").data(cods).join("g").attr("class", "ciudad")
        .attr("transform", (c) => `translate(${pt(ciudades[c])})`).style("cursor", "pointer")
        .on("click", (ev, c) => NODO === "capitales" && filtrarRegion(c))
        .on("mousemove", (ev, c) => { const r = R()[c]; mostrarTip(ev, `<b>${ciudades[c].nombre}</b><br>Censo 2018: ${fmt(ciudades[c].pob2018, 0)} hab.`
          + (r && r.nodo === NODO ? `<br>Índice ${fmt(r.indice, 1)} (${pct(r.var20, 1)})<br>Desempleo ${fmt(r.desempleo, 1)}% · ${r.empresas} empresas` : "")); })
        .on("mouseleave", ocultarTip);
      burb.append("circle").attr("class", "pulso").attr("r", 10);
      burb.append("circle").attr("class", "nucleo");
      burb.append("text").attr("x", 12).attr("y", 4).attr("class", "rotulo").text((c) => NODO === "colombia" ? "Banco de la República · Bogotá" : ciudades[c].nombre);
    }
    // Panel lateral del mapa: leyenda y datos clave.
    const lado = svg.append("g").attr("transform", "translate(640,40)");
    mapa.pintar = () => {
      const reg = R();
      if (NODO === "departamentos") {
        deps.attr("fill", (f) => { const c = COD_DEP[f.properties.cod]; return c && reg[c] ? colorVar(reg[c].var20) : "#131925"; })
          .classed("simulado", (f) => !!COD_DEP[f.properties.cod]).classed("sel", (f) => ui.region && COD_DEP[f.properties.cod] === ui.region);
      } else if (NODO === "colombia") {
        const inf = d3.scaleLinear().domain([0, 3, 8]).range(["#16c784", "#1d2a3f", "#ef4444"]).clamp(true);
        deps.attr("fill", (f) => { const c = COD_DEP[f.properties.cod]; return c && reg[c] ? inf(reg[c].inflacion) : "#1a2333"; })
          .classed("simulado", (f) => !!COD_DEP[f.properties.cod]);
      } else {
        deps.attr("fill", "#141a27");
      }
      if (burb) {
        const caps = {}; misActivos().forEach((a) => caps[a.reg] = (caps[a.reg] || 0) + a.cap);
        const max = Math.max(...Object.values(caps), 1);
        burb.select("circle.nucleo").attr("r", (c) => NODO === "colombia" ? 7 : 4 + 20 * Math.sqrt((caps[c] || 0) / max))
          .attr("fill", (c) => NODO === "colombia" ? COLOR.colombia : reg[c] ? colorVar(reg[c].var20, 0.05) : "#3b82f6")
          .attr("stroke", (c) => ui.region === c ? "#fff" : COLOR[NODO]);
      }
      const filas = NODO === "colombia" ? Object.entries(reg).filter(([, r]) => r.pais === "COL")
        : Object.entries(reg).filter(([, r]) => r.nodo === NODO);
      const datos = filas.sort((a, b) => b[1].var20 - a[1].var20).slice(0, 15);
      lado.selectAll("g.fila").data(datos, (d) => d[0]).join((e) => { const g = e.append("g").attr("class", "fila");
        g.append("rect").attr("class", "barra-f"); g.append("text").attr("class", "f1"); g.append("text").attr("class", "f2"); return g; })
        .attr("transform", (d, i) => `translate(0,${i * 30})`)
        .call((g) => {
          g.select("text.f1").attr("y", 12).text((d) => `${d[0]} · ${d[1].nombre}`);
          g.select("text.f2").attr("y", 12).attr("x", 340).attr("text-anchor", "end")
            .text((d) => NODO === "colombia" ? `infl ${fmt(d[1].inflacion, 1)}%` : pct(d[1].var20, 1))
            .attr("class", (d) => "f2 " + (NODO === "colombia" ? "" : clase(d[1].var20)));
          g.select("rect.barra-f").attr("y", 17).attr("height", 4).attr("rx", 2)
            .attr("width", (d) => NODO === "colombia" ? Math.min(340, d[1].inflacion * 40) : Math.min(340, Math.abs(d[1].var20) * 3400))
            .attr("fill", (d) => NODO === "colombia" ? "#ef4444" : d[1].var20 >= 0 ? "#16c784" : "#ef4444");
        });
    };
  } else {
    const paises = { type: "FeatureCollection", features: geo.paises.features.filter((f) => f.id !== "010") };
    const proj = d3.geoNaturalEarth1().fitExtent([[10, 10], [990, 510]], paises);
    const path = d3.geoPath(proj);
    svg.append("path").attr("d", path({ type: "Sphere" })).attr("class", "esfera");
    svg.append("path").attr("d", path(d3.geoGraticule10())).attr("class", "reticula");
    const codPorId = Object.fromEntries(Object.entries(ISO_NUM).map(([k, v]) => [v, k]));
    const ps = svg.append("g").selectAll("path").data(paises.features).join("path").attr("class", "pais").attr("d", path)
      .on("mousemove", (ev, f) => { const c = codPorId[f.id]; const r = c && R()[c];
        mostrarTip(ev, r ? `<b>${r.nombre}</b><br>Índice ${fmt(r.indice, 1)} (${pct(r.var20, 1)} en 20 días)<br>Tasa ${fmt(r.tasa, 2)}% · inflación ${fmt(r.inflacion, 1)}%
          <br>Desempleo ${fmt(r.desempleo, 1)}% · ${r.empresas} empresas` : c === "COL" ? "<b>Colombia</b><br>cuatro nodos de la red" : (f.properties.name || "")); })
      .on("mouseleave", ocultarTip).on("click", (ev, f) => codPorId[f.id] && codPorId[f.id] !== "COL" && filtrarRegion(codPorId[f.id]));
    const centro = (c) => proj(d3.geoCentroid(paises.features.find((p) => p.id === ISO_NUM[c])));
    const co = centro("COL");
    const arcos = arriba.append("g").selectAll("path").data(Object.keys(ISO2)).join("path").attr("class", "flujo")
      .attr("d", (c) => { const [x2, y2] = centro(c); const mx = (co[0] + x2) / 2, my = Math.min(co[1], y2) - 60; return `M${co[0]},${co[1]} Q${mx},${my} ${x2},${y2}`; });
    arriba.append("circle").attr("cx", co[0]).attr("cy", co[1]).attr("r", 6).attr("class", "col-mundo");
    const et = arriba.append("g").selectAll("text").data(Object.keys(ISO2)).join("text").attr("class", "rotulo")
      .attr("x", (c) => centro(c)[0] + 6).attr("y", (c) => centro(c)[1] - 6).text((c) => c);
    mapa.pintar = () => {
      const reg = R();
      ps.attr("fill", (f) => { const c = codPorId[f.id]; if (c === "COL") return "#4a3512"; return c && reg[c] ? colorVar(reg[c].var20) : "#121722"; })
        .classed("simulado", (f) => !!codPorId[f.id]).classed("sel", (f) => ui.region && codPorId[f.id] === ui.region);
      const flujo = ((st.nodos.internacional || {}).remotas_recibidas || 0) + ((st.nodos.internacional || {}).remotas_enviadas || 0);
      arcos.attr("stroke", COLOR.internacional).attr("stroke-width", (c) => 1 + Math.min(5, flujo / 15) * (reg[c] ? 0.5 + reg[c].empresas / 12 : 0.5))
        .attr("opacity", 0.55);
      et.attr("fill", (c) => reg[c] && reg[c].var20 >= 0 ? "#16c784" : "#ef4444");
    };
  }
  mapa.listo = true;
  mapa.pintar();
  heroe();
});

// ---------- regiones ----------
function regiones() {
  const reg = Object.entries(st.regiones).filter(([, r]) => r.nodo === NODO);
  $("#regiones").innerHTML = reg.map(([cod, r]) => {
    const s = (st.series_region[cod] || []).slice(-60);
    const xs = s.map((p) => p.indice);
    const min = Math.min(...xs), max = Math.max(...xs);
    const linea = xs.length > 1 ? xs.map((v, i) => `${(i / (xs.length - 1)) * 100},${28 - ((v - min) / (max - min || 1)) * 26}`).join(" ") : "";
    return `<div class="region-card ${ui.region === cod ? "sel" : ""}" data-r="${cod}">
      <div class="rc-cab"><b>${NODO === "internacional" ? `<span class="iso">${ISO2[cod] || cod}</span>` : ""}${r.nombre}</b><span class="${clase(r.var20)}">${pct(r.var20, 1)}</span></div>
      <svg viewBox="0 0 100 30" preserveAspectRatio="none" class="spark"><polyline points="${linea}" stroke="${r.var20 >= 0 ? "#16c784" : "#ef4444"}"/></svg>
      <div class="rc-m">índice ${fmt(r.indice, 1)} · infl ${fmt(r.inflacion, 1)}% · desemp ${fmt(r.desempleo, 1)}% · ${r.empresas} emp.</div></div>`;
  }).join("");
  if (NODO === "colombia") {
    const col = ["tunja", "capitales", "departamentos", "colombia"].filter((n) => st.nodos[n]);
    $("#regiones").insertAdjacentHTML("beforeend", `<div class="tenue" style="margin-top:6px">Lo que cada nodo reporta a la junta</div>
      ${col.map((n) => { const i = st.nodos[n].ind; return `<div class="region-card" style="border-left:3px solid ${COLOR[n]};cursor:default">
        <div class="rc-cab"><b style="color:${COLOR[n]}">${NOMBRE[n]}</b><span class="${clase(i.indice - 1000)}">${fmt(i.indice, 1)}</span></div>
        <div class="rc-m">inflación ${fmt(i.inflacion, 2)}% · desempleo ${fmt(i.desempleo, 1)}% · ${i.empresas} empresas</div></div>`; }).join("")}`);
  }
  if (NODO === "tunja" && GEO) {
    const top = [...GEO.boy.features].sort((a, b) => b.properties.pob2018 - a.properties.pob2018).slice(0, 10);
    const max = top[0].properties.pob2018;
    $("#regiones").insertAdjacentHTML("beforeend", `<div class="tenue" style="margin-top:6px">Municipios más poblados de Boyacá (Censo 2018)</div>
      ${top.map((f) => `<div class="barra-sector"><div class="bs-cab"><span>${f.properties.cod === "15001" ? "<b>" + f.properties.nombre + "</b>" : f.properties.nombre}</span>
      <span>${fmt(f.properties.pob2018, 0)}</span></div><div class="bs-fondo"><div style="width:${(100 * f.properties.pob2018 / max).toFixed(1)}%;${f.properties.cod === "15001" ? "" : "opacity:.45"}"></div></div></div>`).join("")}`);
  }
  $("#regiones").querySelectorAll(".region-card").forEach((c) => c.onclick = () => filtrarRegion(c.dataset.r));
}
function filtrarRegion(cod) {
  ui.region = ui.region === cod ? null : cod;
  $("#filtro-region").textContent = ui.region ? `región ${ui.region} · clic de nuevo para quitar` : "";
  regiones(); tabla(); mapa.pintar(); pintarTreemap(true);
}

// ---------- empresas ----------
function tabla() {
  let filas = misActivos();
  if (ui.region) filas = filas.filter((a) => a.reg === ui.region);
  const [k, dir] = ui.orden;
  filas.sort((a, b) => (a[k] > b[k] ? 1 : a[k] < b[k] ? -1 : 0) * dir);
  $("#tabla-activos tbody").innerHTML = filas.map((a) => `<tr data-tk="${a.tk}" class="${a.tk === ui.sel ? "sel" : ""}">
    <td>${a.tk}</td><td class="tenue">${SECTORES[a.sec] || a.sec}</td><td class="num">${fmt(a.p, decimales(a))}</td>
    <td class="num ${clase(a.var)}">${pct(a.var)}</td><td class="num ${clase(a.var_total)}">${pct(a.var_total, 1)}</td></tr>`).join("");
  $("#tabla-activos tbody").querySelectorAll("tr").forEach((tr) => tr.onclick = () => seleccionar(tr.dataset.tk));
}
function encabezadoSel() {
  const a = st.activos[ui.sel];
  if (!a) { if (ui.sel) $("#sel-info").textContent = "Empresa en quiebra: ya no cotiza"; return; }
  $("#sel-ticker").textContent = a.tk;
  $("#sel-info").textContent = `${a.reg} · ${SECTORES[a.sec] || a.sec} · ${a.mon} · cap ${corto(a.cap)}`;
  $("#sel-precio").textContent = fmt(a.p, decimales(a));
  $("#sel-var").textContent = pct(a.var);
  $("#sel-var").className = "var " + clase(a.var);
}
async function seleccionar(tk) { ui.sel = tk; await velas.cargar(tk); encabezadoSel(); tabla(); }

let ultimoTreemap = 0;
function pintarTreemap(forzar) {
  if (!forzar && Date.now() - ultimoTreemap < 2000) return;
  ultimoTreemap = Date.now();
  const nombres = Object.fromEntries(Object.entries(st.regiones).map(([c, r]) => [c, r.nombre]));
  let xs = misActivos();
  if (ui.region) xs = xs.filter((a) => a.reg === ui.region);
  treemap($("#treemap"), xs, { agrupar: (a) => a.reg, etiquetaGrupo: (g) => (nombres[g] || g).toUpperCase(), alto: 360 })
    .on("click", (ev, d) => seleccionar(d.data.a.tk));
}

// ---------- panel especial de cada nodo ----------
function especial() {
  const el = $("#especial-cuerpo");
  const reg = Object.entries(st.regiones).filter(([, r]) => r.nodo === NODO);
  if (NODO === "tunja") {
    const sec = d3.rollups(misActivos(), (v) => ({ cap: d3.sum(v, (a) => a.cap), var: d3.mean(v, (a) => a.var), n: v.length }), (a) => a.sec)
      .sort((a, b) => b[1].cap - a[1].cap);
    const max = d3.max(sec, (s) => s[1].cap) || 1;
    el.innerHTML = sec.map(([s, v]) => `<div class="barra-sector"><div class="bs-cab"><span>${SECTORES[s] || s} <small class="tenue">${v.n} emp.</small></span>
      <span class="${clase(v.var)}">${pct(v.var)}</span></div><div class="bs-fondo"><div style="width:${(100 * v.cap / max).toFixed(1)}%"></div></div>
      <small class="tenue">${corto(v.cap)} COP</small></div>`).join("");
  } else if (NODO === "capitales" || NODO === "departamentos") {
    const filas = reg.sort((a, b) => b[1].indice - a[1].indice);
    el.innerHTML = `<table class="ranking"><thead><tr><th>#</th><th>${NODO === "capitales" ? "Ciudad" : "Departamento"}</th>
      <th class="num">Índice</th><th class="num">20 días</th><th class="num">Desemp.</th><th class="num">Infl.</th></tr></thead><tbody>
      ${filas.map(([c, r], i) => `<tr data-r="${c}"><td>${i + 1}</td><td><b>${r.nombre}</b></td><td class="num">${fmt(r.indice, 1)}</td>
      <td class="num ${clase(r.var20)}">${pct(r.var20, 1)}</td><td class="num">${fmt(r.desempleo, 1)}%</td><td class="num">${fmt(r.inflacion, 1)}%</td></tr>`).join("")}
      </tbody></table>`;
    el.querySelectorAll("tr[data-r]").forEach((tr) => tr.onclick = () => filtrarRegion(tr.dataset.r));
  } else if (NODO === "colombia") {
    const p = st.politica[st.politica.length - 1] || {};
    const juntas = st.politica.filter((x) => x.junta).slice(-6).reverse();
    const infl = p.inflacion ?? 0;
    const ang = Math.max(-1, Math.min(1, (infl - 3) / 5)) * 90;
    el.innerHTML = `<div class="junta">
      <svg viewBox="0 0 200 120" class="medidor"><path d="M20,100 A80,80 0 0 1 180,100" class="m-fondo"/>
        <path d="M20,100 A80,80 0 0 1 100,20" class="m-verde"/><path d="M100,20 A80,80 0 0 1 180,100" class="m-rojo"/>
        <line x1="100" y1="100" x2="100" y2="30" class="aguja" transform="rotate(${ang} 100 100)"/>
        <text x="100" y="92" text-anchor="middle" class="m-valor">${fmt(infl, 2)}%</text>
        <text x="100" y="116" text-anchor="middle" class="m-et">inflación nacional vs meta 3%</text></svg>
      <div class="junta-datos"><div><span class="tenue">Tasa de intervención</span><b>${fmt(p.tasa, 2)}%</b></div>
        <div><span class="tenue">Desempleo nacional</span><b>${fmt(p.desempleo, 1)}%</b></div>
        <div><span class="tenue">Tasa real</span><b>${fmt((p.tasa ?? 0) - infl, 2)}%</b></div></div>
      <div class="tenue" style="margin-top:8px">Últimas juntas</div>
      <ul class="juntas">${juntas.map((j) => `<li><span>${j.fecha || "t" + j.t}</span><b>${fmt(j.tasa, 2)}%</b><span class="tenue">infl ${fmt(j.inflacion, 1)}%</span></li>`).join("") || "<li class='tenue'>La primera junta es en el tick 21</li>"}</ul></div>`;
  } else {
    const m = st.mundo[st.mundo.length - 1] || {};
    el.innerHTML = `<div class="mundo-datos"><div><span class="tenue">TRM</span><b>${fmt(m.trm)}</b></div><div><span class="tenue">Petróleo</span><b>${fmt(m.petroleo)} USD</b></div>
      <div><span class="tenue">Demanda externa</span><b>${fmt((m.demanda_externa || 1) * 100, 1)}</b></div></div>
      <table class="ranking"><thead><tr><th>País</th><th class="num">Tasa</th><th class="num">Infl.</th><th class="num">20 días</th></tr></thead><tbody>
      ${reg.sort((a, b) => b[1].var20 - a[1].var20).map(([c, r]) => `<tr data-r="${c}"><td><span class="iso">${ISO2[c]}</span> ${r.nombre}</td>
        <td class="num">${fmt(r.tasa, 2)}%</td><td class="num">${fmt(r.inflacion, 1)}%</td><td class="num ${clase(r.var20)}">${pct(r.var20, 1)}</td></tr>`).join("")}</tbody></table>`;
    el.querySelectorAll("tr[data-r]").forEach((tr) => tr.onclick = () => filtrarRegion(tr.dataset.r));
  }
}

// ---------- red y agentes ----------
function red() {
  const e = st.nodos[NODO]; if (!e) return;
  const fl = e.flujos || {};
  const max = Math.max(...Object.values(fl), 1);
  $("#red").innerHTML = `<div class="red-resumen"><div><span class="tenue">Enviadas</span><b>${e.remotas_enviadas}</b></div>
    <div><span class="tenue">Recibidas</span><b>${e.remotas_recibidas}</b></div><div><span class="tenue">Pendientes</span><b>${e.ind.pendientes_remotas}</b></div></div>
    ${NODOS.filter((n) => n !== NODO).map((n) => `<div class="barra-sector"><div class="bs-cab"><span style="color:${COLOR[n]}">→ ${NOMBRE[n]}</span><span>${fl[n] || 0}</span></div>
      <div class="bs-fondo"><div style="width:${(100 * (fl[n] || 0) / max).toFixed(1)}%;background:${COLOR[n]}"></div></div></div>`).join("")}`;
  const t = e.ind.por_tipo || {};
  const tot = Object.values(t).reduce((a, b) => a + b, 0) || 1;
  const nombres = { hogar: "Hogares", empresario: "Empresarios", inversionista: "Inversionistas", banco: "Bancos", creador_mercado: "Formador de liquidez" };
  $("#agentes").innerHTML = `<div class="apilada">${Object.entries(t).map(([k, v], i) => `<div style="width:${100 * v / tot}%;background:${PALETA[i]}" title="${nombres[k]}: ${v}"></div>`).join("")}</div>
    ${Object.entries(t).map(([k, v], i) => `<div class="leyenda-f"><i style="background:${PALETA[i]}"></i>${nombres[k] || k}<b>${v}</b></div>`).join("")}
    <div class="leyenda-f tenue">Quiebras personales<b>${e.ind.quiebras_personales}</b></div>`;
}

// ---------- datos ----------
function eventos() { $("#eventos").innerHTML = htmlEventos(st.eventos.filter((e) => e.nodo === NODO || (e.tipo === "choque") || e.texto.includes(NODO))); }
function todoAhora() {
  actualizarReloj(); heroe(); regiones(); tabla(); encabezadoSel(); mapa.pintar(); pintarTreemap(); especial(); red();
}
// Lo caro se pinta como mucho 1 vez por segundo aunque la simulación vaya a máxima velocidad.
const todo = limitar(todoAhora, 1000);
conectar({
  snapshot(s) {
    misRegiones().forEach((cod, i) => serieRegion(cod, i).setData((s.series_region[cod] || []).filter((p) => p.time).map((p) => ({ time: p.time, value: p.indice }))));
    const sn = s.series_nodo[NODO] || [];
    sInfl.setData(sn.map((p) => ({ time: p.time, value: p.inflacion })));
    sDes.setData(sn.map((p) => ({ time: p.time, value: p.desempleo })));
    if (!ui.sel) { const top = misActivos().sort((a, b) => b.cap - a.cap)[0]; if (top) seleccionar(top.tk); }
    eventos(); todo(true); pintarTreemap(true);
  },
  delta(s, d) {
    misRegiones().forEach((cod, i) => { const p = (d.series_region || {})[cod]; if (p && p.time) upd(serieRegion(cod, i), { time: p.time, value: p.indice }); });
    const p = (d.series_nodo || {})[NODO];
    if (p) { upd(sInfl, { time: p.time, value: p.inflacion }); upd(sDes, { time: p.time, value: p.desempleo }); }
    const v = ui.sel && d.velas[ui.sel];
    if (v) velas.nueva(v);
    if (d.eventos && d.eventos.length) eventos();
    todo();
  },
});
document.querySelectorAll("#tabla-activos th").forEach((th) => th.onclick = () => {
  const k = th.dataset.k; ui.orden = [k, ui.orden[0] === k ? -ui.orden[1] : -1]; tabla();
});
panelChoques($("#choques"), NODO);
