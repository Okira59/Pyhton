const SOURCES = [
  "https://raw.githubusercontent.com/Okira59/Pyhton/main/docs/data/",
  "data/",
];
const $ = id => document.getElementById(id);
const fmt = (n, d = 2) => Number(n).toLocaleString("tr-TR", { minimumFractionDigits: d, maximumFractionDigits: d });
const pct = n => (n >= 0 ? "+" : "") + fmt(n, 2) + "%";
const dt = t => new Date(t * 1000).toLocaleString("tr-TR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
const badge = v => v === 1 ? '<span class="badge buy">AL ▲</span>'
                 : v === -1 ? '<span class="badge sell">SAT ▼</span>'
                 : '<span class="badge neutral">nötr</span>';
const side = d => d === 1 ? '<span class="badge buy">AL</span>' : '<span class="badge sell">SAT</span>';
const tzOffset = -new Date().getTimezoneOffset() * 60;  // grafiği yerel saatte göster

async function load(name) {
  for (const base of SOURCES) {
    try {
      const r = await fetch(base + name + ".json?t=" + Date.now(), { cache: "no-store" });
      if (r.ok) return await r.json();
    } catch (e) { /* sıradaki kaynağı dene */ }
  }
  throw new Error(name + ".json yüklenemedi");
}

function positionHtml(pos, price, tp, sl, pip) {
  if (!pos) return '<div class="muted">Açık işlem yok.</div>';
  const target = pos.entry + pos.dir * tp * pip;
  const live = pos.dir * (price - pos.entry) / pos.entry * 100;
  const pips = pos.dir * (price - pos.entry) / pip;
  const stop = sl ? `<div><span class="muted small">Zarar durdur</span><b class="red">${fmt(pos.entry - pos.dir * sl * pip)}</b></div>` : "";
  return `<div class="pos">
    <div><span class="muted small">Yön</span><b>${side(pos.dir)}</b></div>
    <div><span class="muted small">Giriş · ${dt(Date.parse(pos.time) / 1000)}</span><b>${fmt(pos.entry)}</b></div>
    <div><span class="muted small">Kâr al</span><b class="green">${fmt(target)}</b></div>
    ${stop}
    <div><span class="muted small">Anlık kâr/zarar</span><b class="${live >= 0 ? "green" : "red"}">${pct(live)} (${fmt(pips, 1)} pip)</b></div>
  </div>`;
}

function statsHtml(s) {
  if (!s.closed) return '<span class="muted">Kapanan işlem yok.</span>';
  return `<div><span class="muted small">Kapanan</span><br><b>${s.closed}</b></div>
    <div><span class="muted small">Kârlı</span><br><b class="green">${s.wins}</b></div>
    <div><span class="muted small">Zararlı</span><br><b class="red">${s.losses}</b></div>
    <div><span class="muted small">Başarı</span><br><b>${fmt(s.wins / s.closed * 100, 0)}%</b></div>
    <div><span class="muted small">Toplam</span><br><b class="${s.total_pct >= 0 ? "green" : "red"}">${pct(s.total_pct)}</b></div>`;
}

function historyHtml(history) {
  const rows = history.slice().reverse().map(e => {
    if (e.kind === "SINYAL")
      return `<tr><td>${dt(e.t)}</td><td>${e.dir === 1 ? "🟢" : "🔴"} ${side(e.dir)}</td><td>${fmt(e.price)}</td><td></td></tr>`;
    return `<tr><td>${dt(e.t)}</td><td>${e.pct >= 0 ? "✅" : "❌"} KAPAT</td>
      <td>${fmt(e.entry)} → ${fmt(e.exit)}${e.reason ? `<br><span class="muted small">${e.reason}</span>` : ""}</td>
      <td class="${e.pct >= 0 ? "green" : "red"}"><b>${pct(e.pct)}</b></td></tr>`;
  });
  return "<tr><th>Zaman</th><th>Olay</th><th>Fiyat</th><th>Kâr/Zarar</th></tr>" + rows.join("");
}

function setHeader(x) {
  $("price").textContent = "$" + fmt(x.price);
  $("candle").textContent = "son kapanan 15dk mum: " + dt(x.close_time);
  const upd = new Date(Date.parse(x.updated));
  $("updated").textContent = upd.toLocaleString("tr-TR") + ` (${Math.round((Date.now() - upd) / 60000)} dk önce)`;
  $("source").textContent = `${x.source || "Bitget"} ${x.symbol}`;
}

let chart, series, priceLines = [], osc;

// Mum grafiği + sinyal okları; sl verilirse açık işlemin giriş/kâr al/zarar durdur çizgileri
function renderChart(x, sl) {
  if (!chart) {
    chart = LightweightCharts.createChart($("chart"), {
      autoSize: true,
      layout: { background: { color: "#171b23" }, textColor: "#c9cedb" },
      grid: { vertLines: { color: "#20252f" }, horzLines: { color: "#20252f" } },
      timeScale: { timeVisible: true, secondsVisible: false },
      rightPriceScale: { borderColor: "#262c38" },
    });
    series = chart.addCandlestickSeries({
      upColor: "#22c55e", downColor: "#ef4444", wickUpColor: "#22c55e", wickDownColor: "#ef4444", borderVisible: false,
    });
  }
  const candles = x.candles;
  renderOsc(x.osc || []);
  series.setData(candles.map(c => ({ time: c[0] + tzOffset, open: c[1], high: c[2], low: c[3], close: c[4] })));
  const first = candles.length ? candles[0][0] : 0;
  series.setMarkers(x.history.filter(e => e.kind === "SINYAL" && e.t >= first).map(e => ({
    time: e.t - 900 + tzOffset, position: e.dir === 1 ? "belowBar" : "aboveBar",
    color: e.dir === 1 ? "#22c55e" : "#ef4444", shape: e.dir === 1 ? "arrowUp" : "arrowDown",
    text: e.dir === 1 ? "AL" : "SAT" })).sort((a, b) => a.time - b.time));
  priceLines.forEach(l => series.removePriceLine(l));
  priceLines = [];
  const pos = x.position;
  if (pos) {
    const add = (price, color, title) => priceLines.push(series.createPriceLine({ price, color, lineWidth: 1, lineStyle: 2, title }));
    add(pos.entry, "#f5c542", "Giriş");
    add(pos.entry + pos.dir * x.tp_pips * x.pip_size, "#22c55e", "Kâr al");
    if (sl) add(pos.entry - pos.dir * sl * x.pip_size, "#ef4444", "Zarar durdur");
  }
}

function startPage(name, render) {
  async function refresh() {
    try {
      const x = await load(name);
      setHeader(x);
      render(x);
      $("error").style.display = "none";
    } catch (e) {
      $("error").textContent = "Veri alınamadı: " + e.message + " — bir sonraki denemede tekrar denenecek.";
      $("error").style.display = "block";
    }
  }
  refresh();
  setInterval(refresh, 60000);
}

const chartOpts = extra => Object.assign({
  autoSize: true,
  layout: { background: { color: "#171b23" }, textColor: "#c9cedb" },
  grid: { vertLines: { color: "#20252f" }, horzLines: { color: "#20252f" } },
  timeScale: { timeVisible: true, secondsVisible: false },
  rightPriceScale: { borderColor: "#262c38", minimumWidth: 70 },
}, extra);

// Fiyat grafiğinin altında StochRSI ve MACD panelleri (zaman ekseni fiyat grafiğiyle senkron)
function renderOsc(rows) {
  if (!osc) {
    chart.applyOptions({ rightPriceScale: { minimumWidth: 70 } });
    const st = LightweightCharts.createChart($("stoch"), chartOpts());
    const mc = LightweightCharts.createChart($("macd"), chartOpts());
    const line = (c, color) => c.addLineSeries({ color, lineWidth: 1.5, priceLineVisible: false, lastValueVisible: true });
    osc = { st, mc, k: line(st, "#3b82f6"), d: line(st, "#f59e0b"),
            hist: mc.addHistogramSeries({ priceLineVisible: false, lastValueVisible: false }),
            m: line(mc, "#3b82f6"), s: line(mc, "#f59e0b") };
    for (const [v, c] of [[80, "#ef4444"], [20, "#22c55e"]])
      osc.k.createPriceLine({ price: v, color: c, lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: "" });
    osc.k.applyOptions({ autoscaleInfoProvider: () => ({ priceRange: { minValue: 0, maxValue: 100 } }) });
    const charts = [chart, st, mc];
    let syncing = false;
    charts.forEach(src => src.timeScale().subscribeVisibleLogicalRangeChange(r => {
      if (syncing || !r) return;
      syncing = true;
      charts.forEach(c => c !== src && c.timeScale().setVisibleLogicalRange(r));
      syncing = false;
    }));
  }
  const pts = i => rows.map(r => r[i] === null ? { time: r[0] + tzOffset } : { time: r[0] + tzOffset, value: r[i] });
  osc.k.setData(pts(4));
  osc.d.setData(pts(5));
  osc.m.setData(pts(1));
  osc.s.setData(pts(2));
  osc.hist.setData(rows.map(r => r[3] === null ? { time: r[0] + tzOffset }
    : { time: r[0] + tzOffset, value: r[3], color: r[3] >= 0 ? "rgba(34,197,94,.6)" : "rgba(239,68,68,.6)" }));
}
