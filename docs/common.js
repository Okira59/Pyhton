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
  $("candle").textContent = x.live ? "canlı · " + new Date().toLocaleTimeString("tr-TR") : "son kapanan 15dk mum: " + dt(x.close_time);
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

// liveFn verilirse fiyat, grafik ve göstergeler LIVE_MS'de bir tarayıcıda canlı hesaplanır
const LIVE_MS = 10000;
function startPage(name, render, liveFn) {
  let x = null, liveData = null;
  const show = () => { setHeader(x); render(x); };
  async function refresh() {
    try {
      x = Object.assign(await load(name), liveData || {});
      show();
      $("error").style.display = "none";
    } catch (e) {
      $("error").textContent = "Veri alınamadı: " + e.message + " — bir sonraki denemede tekrar denenecek.";
      $("error").style.display = "block";
    }
  }
  async function live() {
    if (!x) return;
    try { liveData = Object.assign(await liveFn(x), { live: true }); Object.assign(x, liveData); show(); }
    catch (e) { console.warn("canlı veri alınamadı", e); }
  }
  refresh().then(() => liveFn && live());
  setInterval(refresh, 60000);
  if (liveFn) setInterval(live, LIVE_MS);
}

const chartOpts = extra => Object.assign({
  autoSize: true,
  layout: { background: { color: "#171b23" }, textColor: "#c9cedb" },
  grid: { vertLines: { color: "#20252f" }, horzLines: { color: "#20252f" } },
  timeScale: { timeVisible: true, secondsVisible: false },
  rightPriceScale: { borderColor: "#262c38", minimumWidth: 70 },
}, extra);

// Fiyat grafiğinin altında StochRSI ve MACD DEMA panelleri (zaman ekseni fiyat grafiğiyle senkron)
function renderOsc(rows) {
  if (!osc) {
    chart.applyOptions({ rightPriceScale: { minimumWidth: 70 } });
    const st = LightweightCharts.createChart($("stoch"), chartOpts());
    const mc = LightweightCharts.createChart($("macd"), chartOpts());
    const line = (c, color) => c.addLineSeries({ color, lineWidth: 1.5, priceLineVisible: false, lastValueVisible: true });
    osc = { st, mc, k: line(st, "#3b82f6"), d: line(st, "#f59e0b"),
            hist: mc.addHistogramSeries({ priceLineVisible: false, lastValueVisible: false }),
            m: line(mc, "#3b82f6"), s: line(mc, "#f59e0b") };
    for (const [v, c] of [[100, "#ef4444"], [0, "#22c55e"]])
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

// ---- canlı göstergeler (Python indicators.py ile aynı formüller) ----
const emaA = (a, p) => { const k = 2 / (p + 1); let prev = null; return a.map(v => prev = prev === null ? v : v * k + prev * (1 - k)); };
const demaA = (a, p) => { const e1 = emaA(a, p), e2 = emaA(e1, p); return e1.map((v, i) => 2 * v - e2[i]); };
const roll = (a, p, fn) => a.map((_, i) => { if (i < p - 1) return null; const w = a.slice(i - p + 1, i + 1); return w.some(v => v === null) ? null : fn(w); });
const mean = w => w.reduce((s, v) => s + v, 0) / w.length;
const std = w => { const m = mean(w); return Math.sqrt(mean(w.map(v => (v - m) ** 2))); };
function rsiA(c, p = 14) {
  const out = [null]; let g = null, l = null;
  for (let i = 1; i < c.length; i++) {
    const d = c[i] - c[i - 1], up = Math.max(d, 0), dn = Math.max(-d, 0);
    g = g === null ? up : g + (up - g) / p; l = l === null ? dn : l + (dn - l) / p;
    out.push(l === 0 ? 100 : 100 - 100 / (1 + g / l));
  }
  return out;
}
function bandsA(close, p = 20, n = 2) {
  const mid = roll(close, p, mean), sd = roll(close, p, std);
  return { mid, up: mid.map((m, i) => m === null ? null : m + n * sd[i]), lo: mid.map((m, i) => m === null ? null : m - n * sd[i]) };
}
function stochA(close, r = rsiA(close)) {
  const rmin = roll(r, 14, w => Math.min(...w)), rmax = roll(r, 14, w => Math.max(...w));
  const st = r.map((v, i) => rmin[i] === null ? null : (v - rmin[i]) / (rmax[i] - rmin[i]) * 100);
  const k = roll(st, 3, mean);
  return { k, d: roll(k, 3, mean) };
}
// TradingView "MACD DEMA": hızlı/yavaş ortalamalar ve sinyal çizgisi EMA yerine DEMA
function macdDemaA(close) {
  const f = demaA(close, 12), sl = demaA(close, 26), m = f.map((v, i) => v - sl[i]), s = demaA(m, 9);
  return { m, s, h: m.map((v, i) => v - s[i]) };
}
const stochBuy = k => k !== null && Math.round(k * 100) / 100 <= 0;     // %K tam 0,00
const stochSell = k => k !== null && Math.round(k * 100) / 100 >= 100;  // %K tam 100,00
const dirOfBools = (b, s) => (b ? 1 : 0) - (s ? 1 : 0);

// rows: [zaman(sn), açılış, yüksek, düşük, kapanış, hacim]
function resampleRows(rows, minutes, origin = "start_day") {
  const sec = minutes * 60, g = new Map();
  for (const x of rows) {
    const day = x[0] - x[0] % 86400, t = origin === "epoch" ? x[0] - x[0] % sec : day + Math.floor((x[0] - day) / sec) * sec;
    const b = g.get(t);
    if (!b) g.set(t, [t, x[1], x[2], x[3], x[4], x[5] || 0]);
    else { b[2] = Math.max(b[2], x[2]); b[3] = Math.min(b[3], x[3]); b[4] = x[4]; b[5] += x[5] || 0; }
  }
  return [...g.values()];
}
const toRows = data => {
  const m = new Map();
  for (const x of data) m.set(Math.floor(x[0] / 1000), [Math.floor(x[0] / 1000), +x[1], +x[2], +x[3], +x[4], +(x[5] || 0)]);
  return [...m.values()].sort((a, b) => a[0] - b[0]);
};
async function tradfiRows(symbol, step) {
  const r = await fetch(`https://www.bitget.com/v1/kline/getMoreKlineDataV2?symbolId=${symbol}&kLineStep=${step}&kLineType=5&endTime=${Date.now() + 3600000}`, { cache: "no-store" });
  const j = await r.json();
  if (j.code !== "00000" || !j.data || !j.data.length) throw new Error(`${symbol} ${step} canlı mum verisi yok`);
  return toRows(j.data).map(x => (x[5] = 0, x));
}
async function bitgetRows(symbol, gran, limit = 1000) {
  const r = await fetch(`https://api.bitget.com/api/v2/mix/market/candles?symbol=${symbol}&productType=USDT-FUTURES&granularity=${gran}&limit=${limit}`, { cache: "no-store" });
  const j = await r.json();
  if (!j.data || !j.data.length) throw new Error(symbol + " için mum verisi yok");
  return toRows(j.data);
}
// grafik altı paneller: [zaman, MACD DEMA, sinyal, histogram, %K, %D]
function oscRows(rows) {
  const close = rows.map(x => x[4]), M = macdDemaA(close), S = stochA(close);
  const num = (v, n) => v === null || isNaN(v) ? null : +v.toFixed(n);
  return rows.map((x, i) => [x[0], num(M.m[i], 3), num(M.s[i], 3), num(M.h[i], 3), num(S.k[i], 2), num(S.d[i], 2)]).slice(-200);
}
