"use strict";
const $ = (s) => document.querySelector(s);
let ALL = [], VIEW = [];
const state = { ustLine: "2.5", iyLine: "1.5", iymsT: "12", ustGroup: "line", iyGroup: "line", iymsGroup: "1", listN: 200 };

const EDGES = {
  fav: [1, 1.25, 1.4, 1.55, 1.7, 1.9, 2.2, 2.6, 99],
  "1": [1, 1.3, 1.5, 1.7, 2.0, 2.4, 3.0, 4.0, 6.0, 99],
  "2": [1, 1.3, 1.5, 1.7, 2.0, 2.4, 3.0, 4.0, 6.0, 99],
  X: [1, 2.9, 3.2, 3.5, 3.8, 4.3, 5.0, 99],
  "o1.5": [1, 1.15, 1.22, 1.3, 1.4, 1.55, 1.75, 99],
  "o2.5": [1, 1.4, 1.6, 1.8, 2.0, 2.3, 2.7, 3.5, 99],
  "o3.5": [1, 1.8, 2.2, 2.6, 3.0, 3.6, 4.5, 6, 99],
  "o4.5": [1, 2.6, 3.2, 4, 5, 6.5, 8, 11, 99],
  "o5.5": [1, 4, 5.5, 7, 9, 12, 16, 999],
  "io0.5": [1, 1.2, 1.3, 1.4, 1.55, 1.75, 2, 99],
  "io1.5": [1, 1.9, 2.2, 2.5, 2.8, 3.2, 3.8, 99],
  "io2.5": [1, 3.5, 4.5, 5.5, 7, 9, 12, 99],
  hf12: [1, 12, 18, 24, 30, 40, 60, 999],
  hf21: [1, 12, 18, 24, 30, 40, 60, 999],
  kgv: [1, 1.5, 1.65, 1.8, 2.0, 2.3, 99],
};
const ONAME = {
  fav: "Favori oranı (MS 1 veya 2'nin düşüğü)", "1": "MS 1 oranı", X: "MS X oranı", "2": "MS 2 oranı",
  "o1.5": "1.5 Üst oranı", "o2.5": "2.5 Üst oranı", "o3.5": "3.5 Üst oranı", "o4.5": "4.5 Üst oranı", "o5.5": "5.5 Üst oranı",
  "io0.5": "İY 0.5 Üst oranı", "io1.5": "İY 1.5 Üst oranı", "io2.5": "İY 2.5 Üst oranı",
  hf12: "İY/MS 1/2 oranı", hf21: "İY/MS 2/1 oranı", kgv: "KG Var oranı",
};

// ---------- yardımcılar ----------
const ot = () => +$("#f-ot").value;
function odd(m, k) {
  if (k === "fav") { const a = odd(m, "1"), b = odd(m, "2"); return a && b ? Math.min(a, b) : null; }
  const v = m.odds[k]; if (!v) return null;
  return v[ot()] || null;
}
const cls = (m, k) => (m.odds[k] ? m.odds[k][0] : null);
const opn = (m, k) => (m.odds[k] ? m.odds[k][1] : null);
const pct = (a, b) => (b ? (100 * a / b) : null);
const f1 = (x) => (x == null ? "-" : x.toFixed(1));
const f2 = (x) => (x == null ? "-" : x.toFixed(2));
const tot = (m) => m.fh + m.fa;
const htTot = (m) => (m.hh == null ? null : m.hh + m.ha);
const htft = (m) => {
  if (m.hh == null) return null;
  const r = (a, b) => (a > b ? "1" : a < b ? "2" : "0");
  return r(m.hh, m.ha) + r(m.fh, m.fa);
};
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
function bucketLabel(e, i) { const lo = e[i], hi = e[i + 1]; return hi >= 99 ? `${f2(lo)} +` : `${f2(lo)} - ${f2(hi - 0.01)}`; }
// renk: genel ortalamaya göre (ortalama = sarı, üstü yeşil, altı kırmızı)
function heat(p, base) {
  if (p == null || !base) return "";
  const h = Math.max(0, Math.min(120, 60 + (p / base - 1) * 120));
  return `style="color:hsl(${h},75%,60%)"`;
}
function baseRate(list, target) { let n = 0, k = 0; for (const m of list) { const t = target(m); if (t == null) continue; n++; if (t) k++; } return pct(k, n); }
function diffCell(d) { return d == null ? "<td>-</td>" : `<td class="${d >= 0 ? "pos" : "neg"}">${d >= 0 ? "+" : ""}${d.toFixed(1)}</td>`; }

// ---------- genel tablo üreticiler ----------
// target: m => true/false/null (null = hesaba katma)
function bucketTable(list, target, key, implKey) {
  const e = EDGES[key];
  const rows = e.slice(0, -1).map(() => ({ n: 0, hit: 0, imp: 0, impN: 0 }));
  let hitsAll = 0;
  for (const m of list) {
    const t = target(m); if (t == null) continue;
    const v = odd(m, key); if (!v) continue;
    let i = e.findIndex((x, j) => v >= x && v < e[j + 1]); if (i < 0) continue;
    const r = rows[i]; r.n++; if (t) { r.hit++; hitsAll++; }
    const iv = implKey ? odd(m, implKey) : null; if (iv) { r.imp += 100 / iv; r.impN++; }
  }
  const base = baseRate(list, target);
  const maxP = Math.max(1, ...rows.map((r) => pct(r.hit, r.n) || 0));
  let h = `<table><tr><th>${ONAME[key]}</th><th>Maç</th><th>Tutan</th><th class="l">Gerçekleşen %</th>${implKey ? "<th>Oranın beklediği %</th><th>Fark</th>" : ""}<th>Tutanların payı %</th></tr>`;
  rows.forEach((r, i) => {
    if (!r.n) return;
    const p = pct(r.hit, r.n), imp = r.impN ? r.imp / r.impN : null;
    h += `<tr class="${r.n < 20 ? "weak" : ""}"><td>${bucketLabel(e, i)}</td><td>${r.n}</td><td>${r.hit}</td>
      <td class="l"><span class="bar" style="width:${(p / maxP) * 120}px"></span><b ${heat(p, base)}>%${f1(p)}</b></td>
      ${implKey ? `<td>%${f1(imp)}</td>${diffCell(imp == null ? null : p - imp)}` : ""}
      <td>%${f1(pct(r.hit, hitsAll))}</td></tr>`;
  });
  return h + "</table>";
}

function condTable(list, target, conds) {
  const base = list.filter((m) => target(m) != null);
  const baseP = pct(base.filter(target).length, base.length);
  let h = `<table><tr><th>Şart</th><th>Maç</th><th>Tutan</th><th class="l">Gerçekleşen %</th><th>Genel ortalamaya göre</th></tr>
    <tr><td><b>Tüm maçlar (genel ortalama)</b></td><td>${base.length}</td><td>${base.filter(target).length}</td><td class="l"><b>%${f1(baseP)}</b></td><td>-</td></tr>`;
  for (const [name, fn] of conds) {
    const s = base.filter((m) => { try { return fn(m); } catch { return false; } });
    const hit = s.filter(target).length, p = pct(hit, s.length);
    h += `<tr class="${s.length < 20 ? "weak" : ""}"><td>${name}</td><td>${s.length}</td><td>${hit}</td>
      <td class="l"><span class="bar" style="width:${Math.min(160, ((p || 0) / (baseP || 1)) * 60)}px"></span><b ${heat(p, baseP)}>%${f1(p)}</b></td>${diffCell(p == null ? null : p - baseP)}</tr>`;
  }
  return h + "</table>";
}

function leagueTable(list, target, minN = 10) {
  const g = {};
  for (const m of list) { const t = target(m); if (t == null) continue; const r = (g[m.lg] ||= { n: 0, hit: 0 }); r.n++; if (t) r.hit++; }
  const rows = Object.entries(g).filter(([, r]) => r.n >= minN).map(([lg, r]) => [lg, r.n, r.hit, pct(r.hit, r.n)]).sort((a, b) => b[3] - a[3]);
  const base = baseRate(list, target), maxP = Math.max(1, ...rows.map((r) => r[3]));
  if (!rows.length) return `<p class="note">Yeterli maç yok (lig başına en az ${minN} maç gerekli).</p>`;
  let h = `<div class="scroll"><table><tr><th>Lig</th><th>Maç</th><th>Tutan</th><th class="l">%</th></tr>`;
  for (const [lg, n, hit, p] of rows) h += `<tr><td>${esc(lg)}</td><td>${n}</td><td>${hit}</td><td class="l"><span class="bar" style="width:${(p / maxP) * 120}px"></span><b ${heat(p, base)}>%${f1(p)}</b></td></tr>`;
  return h + "</table></div>";
}

function moved(m, k, dir) { const c = cls(m, k), o = opn(m, k); if (!c || !o) return false; return dir < 0 ? c <= o * 0.95 : c >= o * 1.05; }
function commonConds(extra = []) {
  return [
    ["Ev sahibi favori (MS1 < MS2)", (m) => odd(m, "1") < odd(m, "2")],
    ["Deplasman favori (MS2 < MS1)", (m) => odd(m, "2") < odd(m, "1")],
    ["Çok net favori var (oran < 1.30)", (m) => odd(m, "fav") < 1.3],
    ["Net favori var (oran 1.30 - 1.60)", (m) => odd(m, "fav") >= 1.3 && odd(m, "fav") < 1.6],
    ["Dengeli maç (iki taraf da 2.30+)", (m) => odd(m, "fav") >= 2.3],
    ["KG Var oranı < 1.70", (m) => odd(m, "kgv") && odd(m, "kgv") < 1.7],
    ["KG Var oranı 2.00+", (m) => odd(m, "kgv") >= 2.0],
    ["2.5 Üst oranı < 1.60", (m) => odd(m, "o2.5") && odd(m, "o2.5") < 1.6],
    ["2.5 Üst oranı 2.20+", (m) => odd(m, "o2.5") >= 2.2],
    ["İY 1.5 Üst oranı < 2.40", (m) => odd(m, "io1.5") && odd(m, "io1.5") < 2.4],
    ["Ev sahibi oranı açılıştan %5+ düştü", (m) => moved(m, "1", -1)],
    ["Deplasman oranı açılıştan %5+ düştü", (m) => moved(m, "2", -1)],
    ...extra,
  ];
}
function pills(items, cur, attr) {
  return `<div class="row">${items.map(([v, t]) => `<button class="pill ${v === cur ? "active" : ""}" data-${attr}="${v}">${t}</button>`).join("")}</div>`;
}
function groupSelect(id, opts, cur) {
  return `<label class="note">Gruplama oranı: <select id="${id}">${opts.map((k) => `<option value="${k}" ${k === cur ? "selected" : ""}>${ONAME[k]}</option>`).join("")}</select></label>`;
}

// ---------- sekmeler ----------
function renderOzet() {
  const L = VIEW, n = L.length;
  const ht = L.filter((m) => m.hh != null);
  const c = (arr, f) => pct(arr.filter(f).length, arr.length);
  const cards = [
    ["Maç sayısı", n, ""],
    ["2.5 Üst", "%" + f1(c(L, (m) => tot(m) > 2.5)), "3+ gol"],
    ["3.5 Üst", "%" + f1(c(L, (m) => tot(m) > 3.5)), "4+ gol"],
    ["4.5 Üst", "%" + f1(c(L, (m) => tot(m) > 4.5)), "5+ gol"],
    ["5.5 Üst", "%" + f1(c(L, (m) => tot(m) > 5.5)), "6+ gol"],
    ["İY 1.5 Üst", "%" + f1(c(ht, (m) => htTot(m) > 1.5)), "ilk yarı 2+ gol"],
    ["İY 2.5 Üst", "%" + f1(c(ht, (m) => htTot(m) > 2.5)), "ilk yarı 3+ gol"],
    ["İY/MS 1/2", "%" + f1(c(ht, (m) => htft(m) === "12")), ht.filter((m) => htft(m) === "12").length + " maç"],
    ["İY/MS 2/1", "%" + f1(c(ht, (m) => htft(m) === "21")), ht.filter((m) => htft(m) === "21").length + " maç"],
  ];
  let h = `<div class="cards">${cards.map(([t, v, s]) => `<div class="card"><div class="t">${t}</div><div class="v">${v}</div><div class="s">${s}</div></div>`).join("")}</div>`;
  h += `<h2>Favori oranına göre sonuç yüzdeleri</h2><p class="note">Satır: maçtaki favorinin (MS 1 veya MS 2'den düşük olanın) oranı. Hücre: o grupta sonucun yüzde kaç gerçekleştiği.</p>`;
  const e = EDGES.fav;
  const cols = [["2.5Ü", (m) => tot(m) > 2.5], ["3.5Ü", (m) => tot(m) > 3.5], ["4.5Ü", (m) => tot(m) > 4.5], ["5.5Ü", (m) => tot(m) > 5.5],
    ["İY 1.5Ü", (m) => (m.hh == null ? null : htTot(m) > 1.5)], ["İY 2.5Ü", (m) => (m.hh == null ? null : htTot(m) > 2.5)],
    ["1/2", (m) => (m.hh == null ? null : htft(m) === "12")], ["2/1", (m) => (m.hh == null ? null : htft(m) === "21")],
    ["KG Var", (m) => m.fh > 0 && m.fa > 0]];
  h += `<div class="scroll"><table><tr><th>Favori oranı</th><th>Maç</th>${cols.map((c) => `<th>${c[0]}</th>`).join("")}</tr>`;
  const bases = cols.map(([, f]) => baseRate(L, f));
  for (let i = 0; i < e.length - 1; i++) {
    const s = L.filter((m) => { const v = odd(m, "fav"); return v && v >= e[i] && v < e[i + 1]; });
    if (!s.length) continue;
    h += `<tr class="${s.length < 20 ? "weak" : ""}"><td>${bucketLabel(e, i)}</td><td>${s.length}</td>`;
    cols.forEach(([, f], j) => { const v = s.filter((m) => f(m) != null); const p = pct(v.filter(f).length, v.length); h += `<td class="heat" ${heat(p, bases[j])}>%${f1(p)}</td>`; });
    h += "</tr>";
  }
  h += "</table></div>";
  h += `<h2>Toplam gol dağılımı</h2>`;
  const dist = {}; L.forEach((m) => { const t = Math.min(tot(m), 7); dist[t] = (dist[t] || 0) + 1; });
  h += `<table><tr><th>Toplam gol</th><th>Maç</th><th class="l">%</th></tr>`;
  for (let t = 0; t <= 7; t++) { const p = pct(dist[t] || 0, n); h += `<tr><td>${t === 7 ? "7+" : t}</td><td>${dist[t] || 0}</td><td class="l"><span class="bar" style="width:${(p || 0) * 3}px"></span>%${f1(p)}</td></tr>`; }
  $("#tab-ozet").innerHTML = h + "</table>";
}

function renderUst() {
  const line = state.ustLine, k = "o" + line, target = (m) => tot(m) > +line;
  const grp = state.ustGroup === "line" ? k : state.ustGroup;
  let h = pills([["2.5", "2.5 Üst"], ["3.5", "3.5 Üst"], ["4.5", "4.5 Üst"], ["5.5", "5.5 Üst"]], line, "ust");
  const withOdds = VIEW.filter((m) => odd(m, k)).length;
  h += `<p class="note">${line} Üst = maçta ${Math.ceil(+line)}+ gol. Bu oranı olan maç: ${withOdds}.</p>`;
  h += groupSelect("g-ust", [k, "fav", "1", "2", "o2.5", "kgv", "io1.5"].filter((v, i, a) => a.indexOf(v) === i), grp);
  h += `<h2>${ONAME[grp]} aralıklarına göre ${line} Üst yüzdesi</h2>`;
  h += bucketTable(VIEW, target, grp, k);
  h += `<h2>Şartlara göre ${line} Üst yüzdesi</h2>`;
  h += condTable(VIEW, target, commonConds([
    [`${line} Üst oranı açılıştan %5+ düştü`, (m) => moved(m, k, -1)],
    [`${line} Üst oranı açılıştan %5+ yükseldi`, (m) => moved(m, k, 1)],
    ["İlk yarı 1.5 üst bitti (2+ gol)", (m) => htTot(m) > 1.5],
    ["İlk yarı golsüz bitti", (m) => htTot(m) === 0],
  ]));
  h += `<h2>Liglere göre ${line} Üst yüzdesi</h2>` + leagueTable(VIEW, target);
  $("#tab-ust").innerHTML = h;
}

function renderIy() {
  const line = state.iyLine, k = "io" + line, target = (m) => (m.hh == null ? null : htTot(m) > +line);
  const grp = state.iyGroup === "line" ? k : state.iyGroup;
  let h = pills([["0.5", "İY 0.5 Üst"], ["1.5", "İY 1.5 Üst"], ["2.5", "İY 2.5 Üst"]], line, "iy");
  h += `<p class="note">İY ${line} Üst = ilk yarıda ${Math.ceil(+line)}+ gol.</p>`;
  h += groupSelect("g-iy", [k, "o2.5", "o3.5", "fav", "kgv"].filter((v, i, a) => a.indexOf(v) === i), grp);
  h += `<h2>${ONAME[grp]} aralıklarına göre İY ${line} Üst yüzdesi</h2>`;
  h += bucketTable(VIEW, target, grp, grp === k ? k : null);
  h += `<h2>Şartlara göre İY ${line} Üst yüzdesi</h2>`;
  h += condTable(VIEW, target, commonConds([
    [`İY ${line} Üst oranı açılıştan %5+ düştü`, (m) => moved(m, k, -1)],
    ["2.5 Üst oranı açılıştan %5+ düştü", (m) => moved(m, "o2.5", -1)],
  ]));
  h += `<h2>Liglere göre İY ${line} Üst yüzdesi</h2>` + leagueTable(VIEW, target);
  $("#tab-iy").innerHTML = h;
}

function renderIyms() {
  const t = state.iymsT, hk = "hf" + t, target = (m) => (m.hh == null ? null : htft(m) === t);
  const grp = state.iymsGroup;
  const ht = VIEW.filter((m) => m.hh != null), hits = ht.filter((m) => htft(m) === t);
  let h = pills([["12", "1/2 (İY ev önde, MS deplasman kazandı)"], ["21", "2/1 (İY deplasman önde, MS ev kazandı)"]], t, "iyms");
  const avg = (arr, k) => { const v = arr.map((m) => odd(m, k)).filter(Boolean); return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null; };
  const comeback = t === "12" ? "2" : "1";
  const favShare = pct(hits.filter((m) => odd(m, comeback) && odd(m, comeback) < odd(m, comeback === "1" ? "2" : "1")).length, hits.length);
  h += `<div class="cards">
    <div class="card"><div class="t">${t[0]}/${t[1]} biten maç</div><div class="v">${hits.length}</div><div class="s">${ht.length} maçta %${f1(pct(hits.length, ht.length))}</div></div>
    <div class="card"><div class="t">Ort. MS 1 oranı</div><div class="v">${f2(avg(hits, "1"))}</div><div class="s">tüm maçlarda ${f2(avg(ht, "1"))}</div></div>
    <div class="card"><div class="t">Ort. MS X oranı</div><div class="v">${f2(avg(hits, "X"))}</div><div class="s">tüm maçlarda ${f2(avg(ht, "X"))}</div></div>
    <div class="card"><div class="t">Ort. MS 2 oranı</div><div class="v">${f2(avg(hits, "2"))}</div><div class="s">tüm maçlarda ${f2(avg(ht, "2"))}</div></div>
    <div class="card"><div class="t">Ort. İY/MS ${t[0]}/${t[1]} oranı</div><div class="v">${f2(avg(hits, hk))}</div><div class="s">tüm maçlarda ${f2(avg(ht, hk))}</div></div>
    <div class="card"><div class="t">Maçı çeviren takım favoriydi</div><div class="v">%${f1(favShare)}</div><div class="s">${comeback === "1" ? "ev sahibi" : "deplasman"} favori</div></div>
  </div>`;
  h += groupSelect("g-iyms", ["1", "2", "fav", "X", hk, "o2.5", "kgv"], grp);
  h += `<h2>${ONAME[grp]} aralıklarına göre ${t[0]}/${t[1]} yüzdesi</h2>`;
  h += bucketTable(VIEW, target, grp, grp === hk ? hk : null);
  h += `<h2>Şartlara göre ${t[0]}/${t[1]} yüzdesi</h2>`;
  h += condTable(VIEW, target, commonConds([["2.5 Üst oranı < 1.70 (gollü maç beklentisi)", (m) => odd(m, "o2.5") && odd(m, "o2.5") < 1.7]]));
  h += `<h2>${t[0]}/${t[1]} biten maçlar</h2><div class="scroll"><table><tr><th>Tarih</th><th class="l">Lig</th><th class="l">Maç</th><th>İY</th><th>MS</th><th>1</th><th>X</th><th>2</th><th>${t[0]}/${t[1]}</th><th>2.5Ü</th></tr>`;
  for (const m of hits.slice(0, 300)) h += `<tr><td>${new Date(m.ts * 1000).toLocaleDateString("tr-TR")}</td><td class="l">${esc(m.lg)}</td><td class="l">${esc(m.h)} - ${esc(m.a)}</td><td>${m.hh}-${m.ha}</td><td>${m.fh}-${m.fa}</td><td>${f2(odd(m, "1"))}</td><td>${f2(odd(m, "X"))}</td><td>${f2(odd(m, "2"))}</td><td>${f2(odd(m, hk))}</td><td>${f2(odd(m, "o2.5"))}</td></tr>`;
  h += "</table></div>" + `<h2>Liglere göre ${t[0]}/${t[1]} yüzdesi</h2>` + leagueTable(VIEW, target);
  $("#tab-iyms").innerHTML = h;
}

function renderListe() {
  const q = (state.q || "").toLowerCase();
  const fl = state.lf || "";
  const L = VIEW.filter((m) => (!q || (m.h + " " + m.a).toLowerCase().includes(q)) && (!fl ||
    (fl === "u25" && tot(m) > 2.5) || (fl === "u35" && tot(m) > 3.5) || (fl === "u45" && tot(m) > 4.5) || (fl === "u55" && tot(m) > 5.5) ||
    (fl === "iy15" && htTot(m) > 1.5) || (fl === "iy25" && htTot(m) > 2.5) || (fl === "12" && htft(m) === "12") || (fl === "21" && htft(m) === "21")));
  let h = `<div class="row"><input id="q" placeholder="Takım ara..." value="${esc(state.q || "")}">
    <select id="lf"><option value="">Tüm sonuçlar</option><option value="u25">2.5 Üst bitenler</option><option value="u35">3.5 Üst bitenler</option><option value="u45">4.5 Üst bitenler</option><option value="u55">5.5 Üst bitenler</option><option value="iy15">İY 1.5 Üst bitenler</option><option value="iy25">İY 2.5 Üst bitenler</option><option value="12">İY/MS 1/2</option><option value="21">İY/MS 2/1</option></select>
    <span class="note">${L.length} maç</span></div>`;
  h += `<div class="scroll"><table><tr><th>Tarih</th><th class="l">Lig</th><th class="l">Maç</th><th>İY</th><th>MS</th><th>1</th><th>X</th><th>2</th><th>1.5Ü</th><th>2.5Ü</th><th>3.5Ü</th><th>4.5Ü</th><th>5.5Ü</th><th>İY1.5Ü</th><th>İY2.5Ü</th><th>KG V</th></tr>`;
  for (const m of L.slice(0, state.listN)) {
    h += `<tr><td>${new Date(m.ts * 1000).toLocaleDateString("tr-TR")}</td><td class="l">${esc(m.lg)}</td><td class="l">${esc(m.h)} - ${esc(m.a)}</td><td>${m.hh == null ? "-" : m.hh + "-" + m.ha}</td><td><b>${m.fh}-${m.fa}</b></td>` +
      ["1", "X", "2", "o1.5", "o2.5", "o3.5", "o4.5", "o5.5", "io1.5", "io2.5", "kgv"].map((k) => `<td>${f2(odd(m, k))}</td>`).join("") + "</tr>";
  }
  h += "</table></div>";
  if (L.length > state.listN) h += `<button class="more" id="more">Daha fazla göster</button>`;
  $("#tab-liste").innerHTML = h;
  $("#lf").value = fl;
}

// ---------- kuponlar ----------
let KUPON = null;
const fmtT = (ts) => new Date(ts * 1000).toLocaleString("tr-TR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
const KIND = { kisa: "4 saatlik", yuksek: "Günlük yüksek oran", iyms: "İY/MS · 4 saatlik", iyms_y: "İY/MS · günlük yüksek oran" };
const isHigh = (k) => k === "yuksek" || k === "iyms_y";
function couponCard(c, top) {
  const st = { "kazandı": ["win", "pos", "TUTTU"], "kaybetti": ["lose", "neg", "YATTI"], "sonuçsuz": ["", "", "Sonuçsuz"] }[c.status] || ["", "", "Bekliyor"];
  let h = `<div class="cp ${st[0]} ${top ? "top" : ""}"><div class="cp-h">
    <span class="tag ${isHigh(c.kind) ? "y" : ""}">${KIND[c.kind] || c.kind} · ${c.legs.length}'lü</span>
    <span>Toplam oran <span class="big">${c.odd.toFixed(2)}</span></span>
    <span>Tutma olasılığı <span class="big" ${heat(c.p * 100, isHigh(c.kind) ? 15 : 35)}>%${f1(c.p * 100)}</span></span>
    <span class="note" style="margin:0">Hazırlandı: ${fmtT(c.created)}</span>
    <span class="st ${st[1]}">${st[2]}</span></div>
    <div class="scroll"><table><tr><th>Saat</th><th class="l">Lig</th><th class="l">Maç</th><th class="l">Tahmin</th><th>Oran</th><th>Olasılık</th><th>Oranın ima ettiği</th><th>Skor (İY / MS)</th></tr>`;
  for (const l of c.legs) {
    const r = l.r === true ? `<span class="pos">✓</span>` : l.r === false ? `<span class="neg">✗</span>` : "";
    h += `<tr><td>${fmtT(l.ts)}</td><td class="l">${esc(l.lg)}</td><td class="l">${esc(l.h)} - ${esc(l.a)}</td><td class="l"><b>${esc(l.pick)}</b></td>
      <td>${l.odd.toFixed(2)}</td><td>%${f1(l.p * 100)}</td><td>%${f1(l.p0 * 100)}</td><td>${l.score ? esc(l.score) + " " + r : "-"}</td></tr>`;
  }
  return h + "</table></div></div>";
}
function renderKupon() {
  const el = $("#tab-kupon");
  if (!KUPON) { el.innerHTML = `<p class="note">Kupon verisi yükleniyor...</p>`; return; }
  const all = KUPON.coupons || [];
  const now = Date.now() / 1000;
  const active = all.filter((c) => c.status === "bekliyor" && Math.max(...c.legs.map((l) => l.ts)) + 2.5 * 3600 > now);
  const done = all.filter((c) => c.status === "kazandı" || c.status === "kaybetti");
  let h = `<p class="note">Kuponlar iddaa bültenindeki oranlardan otomatik hazırlanır: <b>4 saatte bir</b> önümüzdeki 12 saatin maçlarından 3'lü ve 4'lü kuponlar, <b>günde bir kez</b> (09:00 sonrası) o günün maçlarından 2-3 maçlık yüksek oranlı kuponlar.
    <b>İY/MS kuponları</b> aynı zamanlamayla hazırlanır; iddaa İY/MS oranını çoğu maçta yayınlamadığı için bunlarda Flashscore'daki 1xBet oranları kullanılır.
    Olasılık: oranın ima ettiği olasılık, son 3 ayda aynı oran seviyesindeki maçların gerçek sonuçlarına göre düzeltilir. Son güncelleme: ${fmtT(KUPON.updated)}</p>`;
  const sum = (kind) => { const d = done.filter((c) => c.kind === kind); const w = d.filter((c) => c.status === "kazandı"); const ret = w.reduce((s, c) => s + c.odd, 0);
    return `<div class="card"><div class="t">${KIND[kind]} kuponlar (sonuçlanan)</div><div class="v">${w.length} / ${d.length}</div><div class="s">${d.length ? `tutma %${f1((100 * w.length) / d.length)} · 1 birim başına getiri ${(ret / d.length).toFixed(2)}` : "henüz sonuçlanan yok"}</div></div>`; };
  h += `<div class="cards">${sum("kisa")}${sum("yuksek")}${sum("iyms")}${sum("iyms_y")}</div>`;
  const top = KUPON.iyms_top || {};
  if (Object.keys(top).length) {
    h += `<h2>İY/MS seçenekleri: önümüzdeki 36 saatin en olası maçları <span class="note">(Flashscore / 1xBet oranları)</span></h2><div class="scroll"><table><tr><th class="l">Seçenek</th><th>Saat</th><th class="l">Lig</th><th class="l">Maç</th><th>Oran</th><th>Olasılık</th><th>Oranın ima ettiği</th></tr>`;
    for (const [k, rows] of Object.entries(top)) {
      if (!rows.length) { h += `<tr><td class="l"><b>${esc(k)}</b></td><td colspan="6" class="note">uygun maç yok</td></tr>`; continue; }
      rows.forEach((l, i) => (h += `<tr><td class="l">${i ? "" : `<b>${esc(k)}</b>`}</td><td>${fmtT(l.ts)}</td><td class="l">${esc(l.lg)}</td><td class="l">${esc(l.h)} - ${esc(l.a)}</td><td>${l.odd.toFixed(2)}</td><td>%${f1(l.p * 100)}</td><td>%${f1(l.p0 * 100)}</td></tr>`));
    }
    h += `</table></div>`;
  }
  h += `<h2>Aktif kuponlar <span class="note">(tutma olasılığı en yüksek olan en altta)</span></h2>`;
  if (!active.length) h += `<p class="note">Şu an bekleyen kupon yok. Bir sonraki güncellemede hazırlanacak.</p>`;
  const sorted = active.slice().sort((a, b) => a.p - b.p);
  sorted.forEach((c, i) => (h += couponCard(c, i === sorted.length - 1)));
  const past = all.filter((c) => !active.includes(c)).sort((a, b) => b.created - a.created).slice(0, 40);
  if (past.length) { h += `<h2>Geçmiş kuponlar (son 40)</h2>`; past.forEach((c) => (h += couponCard(c, false))); }
  h += `<p class="note">Uyarı: Geçmiş testte (son 45 gün, 1xBet oranları) model olasılıkları gerçekleşenle uyumluydu ama kuponların uzun vadede kâr ettiği görülmedi. Bahis şirketinin marjı nedeniyle kâr garantisi yoktur.</p>`;
  el.innerHTML = h;
}

// ---------- filtre & olaylar ----------
function applyFilters() {
  const src = $("#f-src").value, days = +$("#f-days").value, lg = $("#f-lg").value;
  const cut = Date.now() / 1000 - days * 86400;
  const bySrc = ALL.filter((m) => m.src === src && m.ts >= cut);
  const leagues = [...new Set(bySrc.map((m) => m.lg))].sort();
  const sel = $("#f-lg");
  sel.innerHTML = `<option value="">Tüm ligler (${leagues.length})</option>` + leagues.map((l) => `<option ${l === lg ? "selected" : ""}>${esc(l)}</option>`).join("");
  VIEW = bySrc.filter((m) => !lg || m.lg === lg);
  $("#f-count").textContent = `${VIEW.length} maç analiz ediliyor`;
  renderAll();
}
function renderAll() {
  if (!VIEW.length) {
    const msg = `<p class="note">Bu filtrede maç yok.${$("#f-src").value === "iddaa" ? " iddaa oranları bu uygulama çalıştıkça birikir; ilk günlerde az veri olması normaldir." : ""}</p>`;
    ["ozet", "ust", "iy", "iyms", "liste"].forEach((t) => ($("#tab-" + t).innerHTML = msg));
    renderKupon();
    return;
  }
  renderOzet(); renderUst(); renderIy(); renderIyms(); renderListe(); renderKupon();
}

function showTab(t) {
  if (!document.getElementById("tab-" + t)) return;
  document.querySelectorAll(".tabs button").forEach((x) => x.classList.toggle("active", x.dataset.tab === t));
  document.querySelectorAll(".tab").forEach((x) => x.classList.toggle("active", x.id === "tab-" + t));
}
if (location.hash) showTab(location.hash.slice(1));

document.addEventListener("click", (e) => {
  const b = e.target;
  if (b.dataset.tab) { showTab(b.dataset.tab); history.replaceState(null, "", "#" + b.dataset.tab); } else if (b.dataset.ust) { state.ustLine = b.dataset.ust; state.ustGroup = "line"; renderUst(); }
  else if (b.dataset.iy) { state.iyLine = b.dataset.iy; state.iyGroup = "line"; renderIy(); }
  else if (b.dataset.iyms) { state.iymsT = b.dataset.iyms; renderIyms(); }
  else if (b.id === "more") { state.listN += 300; renderListe(); }
});
document.addEventListener("change", (e) => {
  const id = e.target.id;
  if (id.startsWith("f-")) { state.listN = 200; applyFilters(); }
  else if (id === "g-ust") { state.ustGroup = e.target.value; renderUst(); }
  else if (id === "g-iy") { state.iyGroup = e.target.value; renderIy(); }
  else if (id === "g-iyms") { state.iymsGroup = e.target.value; renderIyms(); }
  else if (id === "lf") { state.lf = e.target.value; state.listN = 200; renderListe(); }
});
let qT;
document.addEventListener("input", (e) => {
  if (e.target.id !== "q") return;
  clearTimeout(qT);
  qT = setTimeout(() => { state.q = e.target.value; renderListe(); const q = $("#q"); q.focus(); q.setSelectionRange(q.value.length, q.value.length); }, 250);
});

fetch("data/matches.json?" + Date.now()).then((r) => r.json()).then((d) => {
  ALL = d.rows.map((r) => Object.fromEntries(d.cols.map((c, i) => [c, r[i]])));
  const fs = ALL.filter((m) => m.src === "fs").length, id = ALL.length - fs;
  $("#meta").textContent = `Son güncelleme: ${new Date(d.updated * 1000).toLocaleString("tr-TR")} · Flashscore: ${fs} maç · iddaa: ${id} maç`;
  applyFilters();
}).catch(() => { $("#meta").textContent = "Veri yüklenemedi (data/matches.json)"; });
fetch("data/kuponlar.json?" + Date.now()).then((r) => r.json()).then((d) => { KUPON = d; renderKupon(); })
  .catch(() => { KUPON = { coupons: [], updated: 0 }; renderKupon(); });
