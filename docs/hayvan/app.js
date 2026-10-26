"use strict";
const KEY = "suru_takip_v1", API0 = "https://online.etb.org.tr/api/v1/Alpha.WebPanel/OnlineKullaniciBulten/GetOnlineBultenSonIslemler", API = API0 + "CH";
const GEBELIK = 150;
const VARSAYILAN_ASI = [
  ["Enterotoksemi (Clostridium karma)", "suru", 0, 0, 180, "Yetişkinlere yılda 2 kez."],
  ["Enterotoksemi – kuzu", "kuzu", 35, 28, 0, "Kuzular 4-6 haftalıkken, 3-4 hafta sonra rapel."],
  ["Enterotoksemi – gebe (doğum öncesi)", "gebe", 35, 0, 0, "Doğumdan 4-6 hafta önce; kuzuya ağız sütüyle bağışıklık geçer."],
  ["Şap", "suru", 0, 0, 180, "Resmi kampanya ile 6 ayda bir."],
  ["Koyun-Keçi Çiçeği", "suru", 0, 0, 365, "Yılda 1 kez."],
  ["Koyun-Keçi Çiçeği – kuzu", "kuzu", 90, 0, 0, "3 aylıktan sonra."],
  ["PPR (Küçük Ruminant Vebası)", "suru", 0, 0, 365, "Resmi program; 3 aylıktan büyüklere."],
  ["PPR – kuzu", "kuzu", 90, 0, 0, "3 aylıktan sonra."],
  ["Brusella (Rev-1) – dişi kuzu", "kuzu", 120, 0, 0, "Dişi kuzulara 3-6 ay arası, ömürde 1 kez (resmi veteriner)."],
  ["Mavi Dil", "suru", 0, 0, 365, "Sinek sezonundan önce (ilkbahar)."],
  ["Şarbon", "suru", 0, 0, 365, "Yılda 1 kez."],
  ["Pastörella", "suru", 0, 0, 180, "Yılda 2 kez."],
  ["İç-dış parazit ilaçlaması", "suru", 0, 0, 180, "İlkbahar ve sonbahar."],
];
const HEDEF = { suru: "Tüm sürü (tekrarlı)", kuzu: "Kuzular (doğuma göre)", gebe: "Gebeler (doğum öncesi)" };

let D = load(), V = location.hash.slice(1) || "ozet", FIYAT = null, CANLI = null, HUB = null, EDIT = null, YEM = "bugday", SIRA = "kupe";
const YEMLER = { bugday: { ad: "Buğday", kod: "KE" }, arpa: { ad: "Arpa", kod: "HBAA" }, kaba: { ad: "Kaba Yem", kod: null } };
const BASLIK = { ozet: "Özet", liste: "Sürü Listesi", kuzu: "Kuzulama", asi: "Aşılar", yem: "Saman/Ot/Yem", maliyet: "Yem Maliyeti", fiyat: "Borsa", hayvan: "Hayvan Ekle/Düzenle", ayar: "Yedek" };

function load() {
  let d = null;
  try { d = JSON.parse(localStorage.getItem(KEY)); } catch (e) {}
  d = d || {};
  for (const k of ["hayvanlar", "kuzulama", "katim", "asilar", "tuketim", "yemFiyat"]) d[k] = d[k] || [];
  if (!d.asiTur) d.asiTur = VARSAYILAN_ASI.map((a, i) => ({ id: "v" + i, ad: a[0], hedef: a[1], ilkGun: a[2], rapelGun: a[3], aralikGun: a[4], not: a[5] }));
  return d;
}
function save(msg) { D.degisti = Date.now(); localStorage.setItem(KEY, JSON.stringify(D)); toast(msg || "Kaydedildi"); render(); }
function toast(m) { const t = document.getElementById("toast"); t.textContent = m; t.style.display = "block"; clearTimeout(toast.h); toast.h = setTimeout(() => t.style.display = "none", 1800); }
const uid = () => Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
const bugun = () => iso(new Date());
const iso = d => { const z = new Date(d.getTime() - d.getTimezoneOffset() * 60000); return z.toISOString().slice(0, 10); };
const ekle = (s, n) => { const d = new Date(s + "T12:00:00"); d.setDate(d.getDate() + n); return iso(d); };
const fark = (a, b) => Math.round((new Date(a + "T12:00:00") - new Date(b + "T12:00:00")) / 864e5);
const trT = s => s ? new Date(s + "T12:00:00").toLocaleDateString("tr-TR", { day: "2-digit", month: "2-digit", year: "numeric" }) : "-";
const num = v => { const n = parseFloat(String(v).replace(",", ".")); return isNaN(n) ? 0 : n; };
const fmt = (n, d = 0) => (+n).toLocaleString("tr-TR", { maximumFractionDigits: d, minimumFractionDigits: d });
const val = id => document.getElementById(id).value.trim();
const opt = (v, t, s) => `<option value="${esc(v)}"${s ? " selected" : ""}>${esc(t)}</option>`;
const kupeList = () => `<datalist id="kupeler">${D.hayvanlar.filter(h => h.aktif !== false).map(h => opt(h.kupe, h.ad || "")).join("")}</datalist>`;
const asiAd = id => (D.asiTur.find(t => t.id === id) || { ad: "?" }).ad;

/* ---------- Aşı hatırlatma hesabı ---------- */
function asiPlani() {
  const out = [], bg = bugun();
  for (const t of D.asiTur) {
    const uyg = D.asilar.filter(a => a.tur === t.id).map(a => a.tarih).sort();
    if (t.hedef === "suru") {
      const son = uyg[uyg.length - 1];
      out.push({ tur: t, tarih: son ? ekle(son, t.aralikGun || 365) : null, acik: son ? "Son uygulama " + trT(son) : "Henüz kayıt yok", adet: null });
    } else if (t.hedef === "kuzu") {
      const g = {};
      for (const k of D.kuzulama) {
        if (!k.sayi || fark(bg, k.tarih) > (t.ilkGun + (t.rapelGun || 0) + 120)) continue;
        const d1 = ekle(k.tarih, t.ilkGun), yap1 = uyg.find(u => u >= ekle(d1, -10));
        let due = null, doz = "1. doz";
        if (!yap1) due = d1;
        else if (t.rapelGun) { const d2 = ekle(yap1, t.rapelGun); if (!uyg.find(u => u >= ekle(d2, -7))) { due = d2; doz = "Rapel"; } }
        if (!due) continue;
        const key = due + doz; (g[key] = g[key] || { tarih: due, doz, adet: 0, anne: 0 }); g[key].adet += +k.sayi; g[key].anne++;
      }
      for (const x of Object.values(g)) out.push({ tur: t, tarih: x.tarih, acik: `${x.doz} · ${x.anne} anneden ${x.adet} kuzu`, adet: x.adet });
    } else if (t.hedef === "gebe") {
      const g = {};
      for (const k of D.katim) {
        const dogum = ekle(k.tarih, GEBELIK);
        if (D.kuzulama.find(z => z.anne === k.anne && z.tarih >= ekle(k.tarih, 100))) continue;
        if (fark(bg, dogum) > 10) continue;
        const due = ekle(dogum, -t.ilkGun);
        if (uyg.find(u => u >= ekle(due, -21) && u <= dogum)) continue;
        (g[due] = g[due] || 0); g[due]++;
      }
      for (const [d, n] of Object.entries(g)) out.push({ tur: t, tarih: d, acik: `${n} gebe (beklenen doğum ${trT(ekle(d, t.ilkGun))})`, adet: n });
    }
  }
  return out.sort((a, b) => (a.tarih || "0000").localeCompare(b.tarih || "0000"));
}
function durum(t) {
  if (!t) return `<span class="tag t-b">Planla</span>`;
  const g = fark(t, bugun());
  if (g < 0) return `<span class="tag t-r">${-g} gün gecikti</span>`;
  if (g === 0) return `<span class="tag t-r">BUGÜN</span>`;
  if (g <= 14) return `<span class="tag t-y">${g} gün kaldı</span>`;
  return `<span class="tag t-g">${g} gün</span>`;
}
function planTablo(liste) {
  if (!liste.length) return `<div class="mut">Yaklaşan aşı yok.</div>`;
  return `<div class="scroll"><table><tr><th>Aşı</th><th>Tarih</th><th>Durum</th></tr>${liste.map(p => `<tr><td><b>${esc(p.tur.ad)}</b><div class="mut">${esc(p.acik)}</div></td><td>${trT(p.tarih)}</td><td>${durum(p.tarih)}</td></tr>`).join("")}</table></div>`;
}

/* ---------- Görünümler ---------- */
const VIEWS = {
  ozet() {
    const bg = bugun(), yil = bg.slice(0, 4), plan = asiPlani();
    const yakin = plan.filter(p => !p.tarih || fark(p.tarih, bg) <= 30);
    const ky = D.kuzulama.filter(k => k.tarih.startsWith(yil));
    const kuzuTop = ky.reduce((s, k) => s + (+k.sayi || 0), 0);
    const tb = D.tuketim.find(t => t.tarih === bg);
    const aktif = D.hayvanlar.filter(h => h.aktif !== false);
    const gebe = D.katim.filter(k => !D.kuzulama.find(z => z.anne === k.anne && z.tarih >= ekle(k.tarih, 100)) && fark(bg, ekle(k.tarih, GEBELIK)) <= 10);
    return `<div class="card"><h2>Borsa – Edirne (TL/kg, baskül)</h2>${fiyatKart(true)}</div>
    <div class="card"><h2>Bugün (${trT(bg)})</h2><div class="grid">
      <div class="stat">Saman<b>${tb ? fmt(tb.saman, 1) : "–"}</b><span class="mut">balya</span></div>
      <div class="stat">Ot<b>${tb ? fmt(tb.ot, 1) : "–"}</b><span class="mut">balya</span></div>
      <div class="stat">Yem<b>${tb ? fmt(tb.yem, 1) : "–"}</b><span class="mut">çuval</span></div></div>
      ${tb ? "" : `<button class="btn" onclick="go('yem')">Bugünkü tüketimi gir</button>`}</div>
    <div class="card"><h2>Yaklaşan / geciken aşılar (30 gün)</h2>${planTablo(yakin)}</div>
    <div class="card"><h2>Sürü – ${yil}</h2><div class="grid">
      <div class="stat">Kayıtlı hayvan<b>${aktif.length}</b></div>
      <div class="stat">Kuzulayan anne<b>${ky.length}</b></div>
      <div class="stat">Doğan kuzu<b>${kuzuTop}</b><span class="mut">${ky.length ? "anne başı " + fmt(kuzuTop / ky.length, 2) : ""}</span></div>
      <div class="stat">Gebe (koç katımı)<b>${gebe.length}</b></div></div></div>`;
  },

  liste() {
    const bg = bugun(), L = D.hayvanlar.filter(h => h.aktif !== false);
    const ay = h => h.dogum ? Math.floor(fark(bg, h.dogum) / 30.44) : null;
    const yasYaz = h => { const a = ay(h); if (a == null) return "-"; const y = Math.floor(a / 12), m = a % 12; return (y ? y + " yaş " : "") + (m || !y ? m + " ay" : ""); };
    const grp = [["Kuzu (0-6 ay)", 0, 6], ["Toklu (6-12 ay)", 6, 12], ["1-2 yaş", 12, 24], ["2-5 yaş", 24, 60], ["5 yaş üstü", 60, 1e9]];
    const sirala = { kupe: (a, b) => a.kupe.localeCompare(b.kupe, "tr", { numeric: true }), yas: (a, b) => (a.dogum || "9999").localeCompare(b.dogum || "9999"), genc: (a, b) => (b.dogum || "").localeCompare(a.dogum || "") }[SIRA];
    const kz = a => D.kuzulama.filter(k => k.anne === a);
    return `<div class="card"><h2>Sürüde ${L.length} hayvan</h2><div class="grid">
      ${grp.map(([ad, a, b]) => `<div class="stat">${ad}<b>${L.filter(h => ay(h) != null && ay(h) >= a && ay(h) < b).length}</b></div>`).join("")}
      <div class="stat">Yaşı bilinmeyen<b>${L.filter(h => !h.dogum).length}</b></div>
      <div class="stat">Dişi / Erkek<b>${L.filter(h => h.cins === "Dişi").length} / ${L.filter(h => h.cins === "Erkek").length}</b></div></div></div>
    <div class="card"><div class="row"><h2>Küpe numaraları ve yaşlar</h2><select style="width:auto" onchange="SIRA=this.value;render()">${opt("kupe", "Küpe no'ya göre", SIRA === "kupe")}${opt("yas", "En yaşlı önce", SIRA === "yas")}${opt("genc", "En genç önce", SIRA === "genc")}</select></div>
      <input placeholder="Ara (küpe no / ad)" oninput="filtre(this.value,'lt')"><div class="scroll"><table id="lt"><tr><th>#</th><th>Küpe no</th><th>Tür</th><th>Doğum</th><th>Yaş</th><th class="n">Kuzulama</th></tr>
      ${[...L].sort(sirala).map((h, i) => { const k = kz(h.kupe); return `<tr onclick="duzenle('hayvanlar','${h.id}');V='hayvan';render()" style="cursor:pointer"><td class="mut">${i + 1}</td><td><b>${esc(h.kupe)}</b>${h.ad ? ` <span class="mut">${esc(h.ad)}</span>` : ""}</td><td>${h.tur} ${h.cins === "Dişi" ? "♀" : "♂"}</td><td>${trT(h.dogum)}</td><td><b>${yasYaz(h)}</b></td><td class="n">${k.length ? `${k.length} / ${k.reduce((s, z) => s + (+z.sayi || 0), 0)} kuzu` : "-"}</td></tr>`; }).join("") || `<tr><td colspan=6 class="mut">Henüz hayvan yok. Aşağıdan toplu ekleyebilirsiniz.</td></tr>`}</table></div>
      <div class="mut">Satıra dokunarak hayvanı düzenleyebilirsiniz. Satılan/ölen hayvanlar listede görünmez.</div></div>
    <div class="card"><h2>Toplu hayvan ekle</h2><div class="mut">Her satıra bir küpe no yazın. İsterseniz yanına boşlukla doğum tarihini (gg.aa.yyyy) veya doğum yılını ekleyin. Örnek:<br>TR220001 15.03.2023<br>TR220002 2021</div>
      <textarea id="tb_liste" rows="6"></textarea>
      <div class="f2"><div><label>Tür</label><select id="tb_tur">${opt("Koyun", "Koyun")}${opt("Keçi", "Keçi")}</select></div><div><label>Cinsiyet</label><select id="tb_cins">${opt("Dişi", "Dişi")}${opt("Erkek", "Erkek")}</select></div></div>
      <button class="btn" onclick="topluEkle()">Ekle</button></div>`;
  },

  maliyet() {
    const y = YEMLER[YEM], son = yemFiyat(YEM), b = borsaYem(YEM);
    const satir = k => { const f = yemFiyat(k), bb = borsaYem(k), x = f ? f.kg : bb && bb.ort;
      return `<tr><td><b>${YEMLER[k].ad}</b><div class="mut">${f ? "Sizin fiyatınız · " + trT(f.tarih) : bb ? "Borsa · " + trT(bb.tarih) : "Fiyat girilmedi"}</div></td><td class="n">${x ? fmt(x, 2) + " ₺" : "-"}</td><td class="n"><b>${x ? fmt(x * 50, 2) + " ₺" : "-"}</b></td></tr>`; };
    const gecmis = D.yemFiyat.filter(x => x.yem === YEM).sort((a, b) => b.tarih.localeCompare(a.tarih));
    return `<div class="secim">${Object.entries(YEMLER).map(([k, v]) => `<button class="${k === YEM ? "on" : ""}" onclick="YEM='${k}';render()">${v.ad}</button>`).join("")}</div>
    <div class="card"><h2>${y.ad} – birim maliyet</h2><div class="grid">
      <div class="stat">1 kg<b class="price">${son ? fmt(son.kg, 2) + " ₺" : "–"}</b><span class="mut">${son ? "alış: " + trT(son.tarih) : "fiyat girin"}</span></div>
      <div class="stat">50 kg (1 çuval)<b class="price">${son ? fmt(son.kg * 50, 2) + " ₺" : "–"}</b><span class="mut">${son && son.not ? esc(son.not) : ""}</span></div></div>
      ${b ? `<h3>Edirne Ticaret Borsası (${trT(b.tarih)})</h3><div class="grid"><div class="stat">1 kg<b>${fmt(b.ort, 2)} ₺</b><span class="mut">${fmt(b.min, 2)} – ${fmt(b.max, 2)}</span></div><div class="stat">50 kg<b>${fmt(b.ort * 50, 2)} ₺</b><span class="mut">${fmt(b.min * 50, 2)} – ${fmt(b.max * 50, 2)}</span></div></div>` : YEM === "kaba" ? `<div class="mut" style="margin-top:8px">Kaba yem borsada işlem görmediği için fiyatı kendiniz girin.</div>` : `<div class="mut">Borsa fiyatı yükleniyor…</div>`}</div>
    <div class="card"><h2>${y.ad} alış fiyatı gir</h2>
      <div class="f2"><div><label>Fiyat (TL)</label><input id="m_fiyat" type="number" step="0.01" inputmode="decimal" oninput="mHesap()"></div>
      <div><label>Birim</label><select id="m_birim" onchange="mHesap()">${opt("1", "1 kg fiyatı")}${opt("50", "50 kg (çuval) fiyatı", true)}</select></div></div>
      <div class="f2"><div><label>Tarih</label><input id="m_tarih" type="date" value="${bugun()}"></div><div><label>Not (satıcı...)</label><input id="m_not"></div></div>
      <div class="mut" id="m_sonuc" style="margin-top:6px"></div>
      <button class="btn" onclick="yemFiyatKaydet()">Kaydet</button>
      ${gecmis.length ? `<h3>Geçmiş alış fiyatları</h3><div class="scroll"><table><tr><th>Tarih</th><th class="n">1 kg</th><th class="n">50 kg</th><th></th></tr>${gecmis.map(x => `<tr><td>${trT(x.tarih)}${x.not ? `<div class="mut">${esc(x.not)}</div>` : ""}</td><td class="n">${fmt(x.kg, 2)} ₺</td><td class="n">${fmt(x.kg * 50, 2)} ₺</td><td class="n"><button class="del" onclick="sil('yemFiyat','${x.id}')">Sil</button></td></tr>`).join("")}</table></div>` : ""}</div>
    <div class="card"><h2>Tüm yemler</h2><div class="scroll"><table><tr><th>Yem</th><th class="n">1 kg</th><th class="n">50 kg</th></tr>${Object.keys(YEMLER).map(satir).join("")}</table></div></div>`;
  },

  kuzu() {
    const e = EDIT && EDIT.tip === "kuzulama" ? D.kuzulama.find(x => x.id === EDIT.id) : null;
    const k = e || { tarih: bugun(), sayi: 1, erkek: "", disi: "", olu: "" };
    const yil = {};
    for (const x of D.kuzulama) { const y = x.tarih.slice(0, 4); (yil[y] = yil[y] || { a: 0, k: 0, e: 0, d: 0, o: 0, ikiz: 0 }); const s = yil[y]; s.a++; s.k += +x.sayi || 0; s.e += +x.erkek || 0; s.d += +x.disi || 0; s.o += +x.olu || 0; if (+x.sayi >= 2) s.ikiz++; }
    const bg = bugun();
    const bekl = D.katim.map(x => ({ ...x, dogum: ekle(x.tarih, GEBELIK) })).filter(x => !D.kuzulama.find(z => z.anne === x.anne && z.tarih >= ekle(x.tarih, 100))).sort((a, b) => a.dogum.localeCompare(b.dogum));
    return `<div class="card"><h2>${e ? "Kuzulamayı düzenle" : "Yeni kuzulama"}</h2>${kupeList()}
      <div class="f2"><div><label>Anne küpe no</label><input id="k_anne" list="kupeler" value="${esc(k.anne || "")}" placeholder="örn. TR22..."></div>
      <div><label>Kuzulama tarihi</label><input id="k_tarih" type="date" value="${k.tarih}"></div></div>
      <div class="f2"><div><label>Kaç kuzu doğurdu</label><input id="k_sayi" type="number" min="0" inputmode="numeric" value="${k.sayi}"></div>
      <div><label>Ölü doğan</label><input id="k_olu" type="number" min="0" inputmode="numeric" value="${k.olu || ""}"></div></div>
      <div class="f2"><div><label>Erkek</label><input id="k_erkek" type="number" min="0" inputmode="numeric" value="${k.erkek || ""}"></div>
      <div><label>Dişi</label><input id="k_disi" type="number" min="0" inputmode="numeric" value="${k.disi || ""}"></div></div>
      <label>Not (kuzu küpe no, doğum ağırlığı...)</label><input id="k_not" value="${esc(k.not || "")}">
      <button class="btn" onclick="kuzuKaydet()">Kaydet</button>${e ? ` <button class="btn sec" onclick="EDIT=null;render()">Vazgeç</button>` : ""}</div>
    <div class="card"><h2>Yıllık özet</h2><div class="scroll"><table><tr><th>Yıl</th><th class="n">Anne</th><th class="n">Kuzu</th><th class="n">Erkek</th><th class="n">Dişi</th><th class="n">Ölü</th><th class="n">İkiz+</th><th class="n">Anne başı</th></tr>
      ${Object.keys(yil).sort().reverse().map(y => { const s = yil[y]; return `<tr><td>${y}</td><td class="n">${s.a}</td><td class="n">${s.k}</td><td class="n">${s.e}</td><td class="n">${s.d}</td><td class="n">${s.o}</td><td class="n">${s.ikiz}</td><td class="n">${fmt(s.k / s.a, 2)}</td></tr>`; }).join("") || `<tr><td colspan=8 class="mut">Kayıt yok</td></tr>`}</table></div></div>
    <div class="card"><h2>Kuzulama kayıtları</h2><input placeholder="Ara (küpe no / tarih)" oninput="filtre(this.value,'kt')"><div class="scroll"><table id="kt"><tr><th>Tarih</th><th>Anne</th><th class="n">Kuzu</th><th class="n">E/D</th><th></th></tr>
      ${[...D.kuzulama].sort((a, b) => b.tarih.localeCompare(a.tarih)).map(x => `<tr><td>${trT(x.tarih)}</td><td>${esc(x.anne)}${x.not ? `<div class="mut">${esc(x.not)}</div>` : ""}</td><td class="n"><b>${x.sayi}</b>${+x.olu ? ` <span class="mut">(${x.olu} ölü)</span>` : ""}</td><td class="n">${x.erkek || 0}/${x.disi || 0}</td><td class="n"><button class="ed" onclick="duzenle('kuzulama','${x.id}')">Düzenle</button><button class="del" onclick="sil('kuzulama','${x.id}')">Sil</button></td></tr>`).join("") || `<tr><td colspan=5 class="mut">Kayıt yok</td></tr>`}</table></div></div>
    <div class="card"><h2>Koç katımı / beklenen doğumlar</h2><div class="mut">Gebelik ~${GEBELIK} gün kabul edilir. Doğum kaydı girilince listeden düşer.</div>
      <div class="f2"><div><label>Anne küpe no</label><input id="c_anne" list="kupeler"></div><div><label>Koç katım tarihi</label><input id="c_tarih" type="date" value="${bg}"></div></div>
      <button class="btn" onclick="katimKaydet()">Katım ekle</button>
      <div class="scroll"><table><tr><th>Anne</th><th>Katım</th><th>Beklenen doğum</th><th></th><th></th></tr>${bekl.map(x => `<tr><td>${esc(x.anne)}</td><td>${trT(x.tarih)}</td><td>${trT(x.dogum)}</td><td>${durum(x.dogum)}</td><td><button class="del" onclick="sil('katim','${x.id}')">Sil</button></td></tr>`).join("") || `<tr><td colspan=5 class="mut">Bekleyen gebelik yok</td></tr>`}</table></div></div>`;
  },

  asi() {
    const plan = asiPlani();
    const e = EDIT && EDIT.tip === "asilar" ? D.asilar.find(x => x.id === EDIT.id) : null;
    const a = e || { tarih: bugun(), hedef: "Tüm sürü" };
    const te = EDIT && EDIT.tip === "asiTur" ? D.asiTur.find(x => x.id === EDIT.id) : null;
    const t = te || { hedef: "suru", ilkGun: 0, rapelGun: 0, aralikGun: 365 };
    return `<div class="card"><h2>Aşı takvimi – ne zaman yapılmalı?</h2>${planTablo(plan)}
      <div class="mut" style="margin-top:8px">Hesap: sürü aşıları son uygulama + tekrar aralığı; kuzu aşıları kuzulama tarihine göre; gebe aşıları koç katımı + ${GEBELIK} gün doğum tarihine göre. Genel bilgidir, bölgenize göre veterinerinize danışın.</div></div>
    <div class="card"><h2>${e ? "Aşı kaydını düzenle" : "Yapılan aşıyı kaydet"}</h2>
      <label>Aşı</label><select id="a_tur">${D.asiTur.map(x => opt(x.id, x.ad, x.id === a.tur)).join("")}</select>
      <div class="f2"><div><label>Tarih</label><input id="a_tarih" type="date" value="${a.tarih}"></div><div><label>Kaç hayvan</label><input id="a_adet" type="number" inputmode="numeric" value="${a.adet || ""}"></div></div>
      <label>Kime yapıldı</label><input id="a_hedef" value="${esc(a.hedef || "")}" placeholder="Tüm sürü / Kuzular / küpe no'lar">
      <label>Not (aşı adı/seri no, veteriner)</label><input id="a_not" value="${esc(a.not || "")}">
      <button class="btn" onclick="asiKaydet()">Kaydet</button>${e ? ` <button class="btn sec" onclick="EDIT=null;render()">Vazgeç</button>` : ""}</div>
    <div class="card"><h2>Yapılan aşılar</h2><div class="scroll"><table><tr><th>Tarih</th><th>Aşı</th><th>Kime</th><th class="n">Adet</th><th></th></tr>
      ${[...D.asilar].sort((a, b) => b.tarih.localeCompare(a.tarih)).map(x => `<tr><td>${trT(x.tarih)}</td><td>${esc(asiAd(x.tur))}${x.not ? `<div class="mut">${esc(x.not)}</div>` : ""}</td><td>${esc(x.hedef)}</td><td class="n">${x.adet || ""}</td><td class="n"><button class="ed" onclick="duzenle('asilar','${x.id}')">Düzenle</button><button class="del" onclick="sil('asilar','${x.id}')">Sil</button></td></tr>`).join("") || `<tr><td colspan=5 class="mut">Kayıt yok</td></tr>`}</table></div></div>
    <div class="card"><h2>Aşı türleri ve aralıkları</h2><div class="scroll"><table><tr><th>Aşı</th><th>Hedef</th><th>Zamanlama</th><th></th></tr>
      ${D.asiTur.map(x => `<tr><td><b>${esc(x.ad)}</b><div class="mut">${esc(x.not || "")}</div></td><td>${HEDEF[x.hedef]}</td><td>${x.hedef === "suru" ? `her ${x.aralikGun} gün` : x.hedef === "kuzu" ? `doğumdan ${x.ilkGun} gün sonra${x.rapelGun ? `, rapel +${x.rapelGun} gün` : ""}` : `doğumdan ${x.ilkGun} gün önce`}</td><td class="n"><button class="ed" onclick="duzenle('asiTur','${x.id}')">Düzenle</button><button class="del" onclick="sil('asiTur','${x.id}')">Sil</button></td></tr>`).join("")}</table></div>
      <h3>${te ? "Aşı türünü düzenle" : "Yeni aşı türü ekle"}</h3>
      <label>Aşı adı</label><input id="t_ad" value="${esc(t.ad || "")}">
      <label>Hedef</label><select id="t_hedef">${Object.entries(HEDEF).map(([k, v]) => opt(k, v, k === t.hedef)).join("")}</select>
      <div class="f3"><div><label>Tekrar aralığı (gün) – sürü</label><input id="t_aralik" type="number" value="${t.aralikGun || ""}"></div>
      <div><label>Doğumdan gün (kuzu: sonra, gebe: önce)</label><input id="t_ilk" type="number" value="${t.ilkGun || ""}"></div>
      <div><label>Rapel (gün sonra) – kuzu</label><input id="t_rapel" type="number" value="${t.rapelGun || ""}"></div></div>
      <label>Not</label><input id="t_not" value="${esc(t.not || "")}">
      <button class="btn" onclick="turKaydet()">Kaydet</button>${te ? ` <button class="btn sec" onclick="EDIT=null;render()">Vazgeç</button>` : ""}</div>`;
  },

  yem() {
    const bg = bugun(), t = D.tuketim.find(x => x.tarih === (EDIT && EDIT.tip === "tuketim" ? EDIT.id : bg)) || { tarih: EDIT && EDIT.tip === "tuketim" ? EDIT.id : bg };
    const L = [...D.tuketim].sort((a, b) => b.tarih.localeCompare(a.tarih));
    const top = (from, k) => D.tuketim.filter(x => x.tarih >= from && x.tarih <= bg).reduce((s, x) => s + (+x[k] || 0), 0);
    const g7 = ekle(bg, -6), ay = bg.slice(0, 8) + "01", g30 = ekle(bg, -29);
    const gun = (from) => Math.max(1, D.tuketim.filter(x => x.tarih >= from && x.tarih <= bg).length);
    const satir = (ad, k, b) => `<tr><td>${ad}</td><td class="n">${fmt(top(g7, k), 1)}</td><td class="n">${fmt(top(g7, k) / gun(g7), 1)}</td><td class="n">${fmt(top(ay, k), 1)}</td><td class="n">${fmt(top(g30, k) / gun(g30), 1)}</td><td class="mut">${b}</td></tr>`;
    return `<div class="card"><h2>Günlük tüketim girişi</h2>
      <label>Tarih</label><input id="y_tarih" type="date" value="${t.tarih}" onchange="EDIT={tip:'tuketim',id:this.value};render()">
      <div class="f3"><div><label>Saman (balya)</label><input id="y_saman" type="number" step="0.5" inputmode="decimal" value="${t.saman ?? ""}"></div>
      <div><label>Ot (balya)</label><input id="y_ot" type="number" step="0.5" inputmode="decimal" value="${t.ot ?? ""}"></div>
      <div><label>Yem (çuval)</label><input id="y_yem" type="number" step="0.5" inputmode="decimal" value="${t.yem ?? ""}"></div></div>
      <label>Not</label><input id="y_not" value="${esc(t.not || "")}">
      <button class="btn" onclick="yemKaydet()">${D.tuketim.find(x => x.tarih === t.tarih) ? "Güncelle" : "Kaydet"}</button>
      <button class="btn sec" onclick="dunKopyala()">Dünkü değerleri getir</button></div>
    <div class="card"><h2>Özet</h2><div class="scroll"><table><tr><th></th><th class="n">Son 7 gün</th><th class="n">Günlük ort. (7g)</th><th class="n">Bu ay</th><th class="n">Günlük ort. (30g)</th><th></th></tr>
      ${satir("Saman", "saman", "balya")}${satir("Ot", "ot", "balya")}${satir("Yem", "yem", "çuval")}</table></div>
      ${grafikYem(L.slice(0, 30).reverse())}</div>
    <div class="card"><h2>Kayıtlar</h2><div class="scroll"><table><tr><th>Tarih</th><th class="n">Saman</th><th class="n">Ot</th><th class="n">Yem</th><th></th></tr>
      ${L.map(x => `<tr><td>${trT(x.tarih)}${x.not ? `<div class="mut">${esc(x.not)}</div>` : ""}</td><td class="n">${fmt(x.saman || 0, 1)}</td><td class="n">${fmt(x.ot || 0, 1)}</td><td class="n">${fmt(x.yem || 0, 1)}</td><td class="n"><button class="ed" onclick="EDIT={tip:'tuketim',id:'${x.tarih}'};render();scrollTo(0,0)">Düzenle</button><button class="del" onclick="sil('tuketim','${x.tarih}','tarih')">Sil</button></td></tr>`).join("") || `<tr><td colspan=5 class="mut">Kayıt yok</td></tr>`}</table></div></div>`;
  },

  fiyat() {
    const g = (FIYAT && FIYAT.gecmis) || [];
    const kuzu = g.filter(x => x.kod === "1102002"), sut = g.filter(x => x.kod === "1102004");
    const son = birlesik();
    return `<div class="card"><h2>Edirne Ticaret Borsası – canlı hayvan salonu</h2>${fiyatKart(false)}
      <div class="mut" style="margin-top:6px">Fiyatlar baskül (canlı kg) TL/kg. Tarih, o ürünün borsada son işlem gördüğü gündür. Kaynak: online.etb.org.tr</div></div>
    <div class="card"><h2>Kuzu değeri hesapla</h2><div class="f2"><div><label>Canlı ağırlık (kg)</label><input id="h_kg" type="number" inputmode="decimal" oninput="hesap()"></div>
      <div><label>Ürün</label><select id="h_urun" onchange="hesap()">${Object.values(son).filter(x => x.kod.startsWith("1102")).sort((a, b) => (a.kod === "1102002" ? -2 : a.kod === "1102004" ? -1 : 0) - (b.kod === "1102002" ? -2 : b.kod === "1102004" ? -1 : 0)).map(x => opt(x.kod, x.urun)).join("")}</select></div></div>
      <div class="big price" id="h_sonuc" style="margin-top:8px">–</div></div>
    <div class="card"><h2>Kuzu – fiyat geçmişi</h2>${grafikFiyat(kuzu)}${tabloFiyat(kuzu)}</div>
    <div class="card"><h2>Süt Kuzusu – fiyat geçmişi</h2>${grafikFiyat(sut)}${tabloFiyat(sut)}</div>
    <div class="card"><h2>Diğer küçükbaş (son işlem)</h2><div class="scroll"><table><tr><th>Ürün</th><th>Tarih</th><th class="n">En az</th><th class="n">En çok</th><th class="n">Ortalama</th><th class="n">Hayvan</th></tr>
      ${Object.values(son).filter(x => x.kod.startsWith("1102")).map(x => `<tr><td>${esc(x.urun)}</td><td>${trT(x.tarih)}</td><td class="n">${fmt(x.min, 2)}</td><td class="n">${fmt(x.max, 2)}</td><td class="n"><b>${fmt(x.ort, 2)}</b></td><td class="n">${x.hayvan ?? ""}</td></tr>`).join("")}</table></div></div>`;
  },

  hayvan() {
    const e = EDIT && EDIT.tip === "hayvanlar" ? D.hayvanlar.find(x => x.id === EDIT.id) : null;
    const h = e || { tur: "Koyun", cins: "Dişi" };
    const kz = a => D.kuzulama.filter(k => k.anne === a);
    return `<div class="card"><h2>${e ? "Hayvanı düzenle" : "Hayvan ekle"}</h2>
      <div class="f2"><div><label>Küpe no</label><input id="h_kupe" value="${esc(h.kupe || "")}"></div><div><label>Ad / işaret</label><input id="h_ad" value="${esc(h.ad || "")}"></div></div>
      <div class="f3"><div><label>Tür</label><select id="h_tur">${["Koyun", "Keçi"].map(x => opt(x, x, x === h.tur)).join("")}</select></div>
      <div><label>Cinsiyet</label><select id="h_cins">${["Dişi", "Erkek"].map(x => opt(x, x, x === h.cins)).join("")}</select></div>
      <div><label>Doğum tarihi</label><input id="h_dogum" type="date" value="${h.dogum || ""}"></div></div>
      <label>Not (ırk, satış/ölüm...)</label><input id="h_not" value="${esc(h.not || "")}">
      <label><input type="checkbox" id="h_aktif" style="width:auto" ${h.aktif === false ? "" : "checked"}> Sürüde (satıldı/öldüyse işareti kaldırın)</label>
      <button class="btn" onclick="hayvanKaydet()">Kaydet</button>${e ? ` <button class="btn sec" onclick="EDIT=null;render()">Vazgeç</button>` : ""}
      <div class="mut" style="margin-top:6px">Hayvan kaydı zorunlu değildir; kuzulama ve aşıyı doğrudan küpe no yazarak da girebilirsiniz.</div></div>
    <div class="card"><h2>Hayvanlar (${D.hayvanlar.filter(x => x.aktif !== false).length} sürüde)</h2><input placeholder="Ara" oninput="filtre(this.value,'ht')"><div class="scroll"><table id="ht"><tr><th>Küpe</th><th>Tür</th><th>Yaş</th><th class="n">Kuzulama</th><th></th></tr>
      ${D.hayvanlar.map(x => { const k = kz(x.kupe); return `<tr style="${x.aktif === false ? "opacity:.5" : ""}"><td><b>${esc(x.kupe)}</b> ${esc(x.ad || "")}${x.not ? `<div class="mut">${esc(x.not)}</div>` : ""}</td><td>${x.tur} ${x.cins === "Dişi" ? "♀" : "♂"}</td><td>${x.dogum ? fmt(fark(bugun(), x.dogum) / 365, 1) : "-"}</td><td class="n">${k.length ? `${k.length} kez / ${k.reduce((s, z) => s + (+z.sayi || 0), 0)} kuzu` : "-"}</td><td class="n"><button class="ed" onclick="duzenle('hayvanlar','${x.id}')">Düzenle</button><button class="del" onclick="sil('hayvanlar','${x.id}')">Sil</button></td></tr>`; }).join("") || `<tr><td colspan=5 class="mut">Kayıt yok</td></tr>`}</table></div></div>`;
  },

  ayar() {
    return `<div class="card"><h2>Yedekleme</h2><div class="mut">Girdiğiniz bilgiler bu telefonda/tarayıcıda saklanır. Telefon değiştirirken veya tarayıcı verisi silinmeden önce yedek alın.
      Son değişiklik: ${D.degisti ? new Date(D.degisti).toLocaleString("tr-TR") : "-"}${D.yedek ? " · Son yedek: " + new Date(D.yedek).toLocaleString("tr-TR") : ""}</div>
      <button class="btn" onclick="yedekAl()">Yedek dosyası indir</button>
      <label style="margin-top:14px">Yedekten geri yükle</label><input type="file" accept=".json,application/json" onchange="yedekYukle(this.files[0])">
      <button class="btn sec" onclick="csvAl()">Excel için CSV indir</button></div>
    <div class="card"><h2>Hatırlatma bildirimi</h2><div class="mut">Uygulama açıldığında geciken/bugün yapılacak aşı varsa bildirim gösterir.</div>
      <button class="btn sec" onclick="Notification.requestPermission().then(p=>toast(p==='granted'?'Bildirim açık':'İzin verilmedi'))">Bildirim izni ver</button></div>
    <div class="card"><h2>Tüm verileri sil</h2><button class="btn" style="background:var(--r)" onclick="if(confirm('Tüm kayıtlar silinsin mi? Geri alınamaz.')){localStorage.removeItem(KEY);D=load();save('Silindi')}">Sıfırla</button></div>`;
  },
};

/* ---------- Fiyat yardımcıları ---------- */
function birlesik() {
  const s = { ...((FIYAT && FIYAT.son) || {}) };
  for (const x of CANLI || []) if (/^110200[1-7]$/.test(x.UrunKodu)) {
    const o = s[x.UrunKodu];
    if (!o || x.Tarih >= o.tarih) s[x.UrunKodu] = { kod: x.UrunKodu, urun: x.UrunAdi, tarih: x.Tarih, min: x.MinFiyat, max: x.MaxFiyat, ort: x.OrtFiyat, hayvan: x.Adet, kg: x.IslemMiktari };
  }
  return s;
}
function fiyatKart(kisa) {
  const s = birlesik();
  if (!Object.keys(s).length) return `<div class="mut">Fiyatlar yükleniyor…</div>`;
  const kart = k => { const x = s[k]; if (!x) return ""; const eski = fark(bugun(), x.tarih);
    return `<div class="stat"><span>${esc(x.urun)}</span><b class="price">${fmt(x.ort, 2)} ₺</b><span class="mut">${fmt(x.min, 2)} – ${fmt(x.max, 2)} · ${trT(x.tarih)}${eski > 0 ? ` (${eski} gün önce)` : " (bugün)"}${x.hayvan ? ` · ${x.hayvan} baş` : ""}</span></div>`; };
  return `<div class="grid">${kart("1102004")}${kart("1102002")}${kisa ? "" : kart("1102006") + kart("1102001")}</div>`;
}
function tabloFiyat(l) {
  if (!l.length) return "";
  return `<div class="scroll" style="max-height:260px;overflow-y:auto"><table><tr><th>Tarih</th><th class="n">En az</th><th class="n">En çok</th><th class="n">Ort.</th><th class="n">Baş</th></tr>${[...l].reverse().map(x => `<tr><td>${trT(x.tarih)}</td><td class="n">${fmt(x.min, 2)}</td><td class="n">${fmt(x.max, 2)}</td><td class="n"><b>${fmt(x.ort, 2)}</b></td><td class="n">${x.hayvan ?? ""}</td></tr>`).join("")}</table></div>`;
}
function grafikFiyat(l) {
  if (l.length < 2) return `<div class="mut">Grafik için en az 2 günlük veri gerekiyor; uygulama her gün borsa fiyatını kaydeder.</div>`;
  const W = 600, H = 160, P = 30, v = l.map(x => x.ort), mn = Math.min(...l.map(x => x.min)), mx = Math.max(...l.map(x => x.max));
  const X = i => P + i * (W - P - 8) / (l.length - 1), Y = y => H - 18 - (y - mn) / ((mx - mn) || 1) * (H - 30);
  const pts = v.map((y, i) => `${X(i)},${Y(y)}`).join(" ");
  const band = l.map((x, i) => `${X(i)},${Y(x.max)}`).join(" ") + " " + [...l].reverse().map((x, j) => `${X(l.length - 1 - j)},${Y(x.min)}`).join(" ");
  return `<svg viewBox="0 0 ${W} ${H}" width="100%"><polygon points="${band}" fill="#eab30822"/><polyline points="${pts}" fill="none" stroke="#eab308" stroke-width="2"/>
    <text x="0" y="${Y(mx) + 4}">${fmt(mx)}</text><text x="0" y="${Y(mn)}">${fmt(mn)}</text><text x="${P}" y="${H - 2}">${trT(l[0].tarih)}</text><text x="${W - 70}" y="${H - 2}">${trT(l[l.length - 1].tarih)}</text></svg>`;
}
function grafikYem(l) {
  if (!l.length) return "";
  const W = 600, H = 140, mx = Math.max(1, ...l.map(x => Math.max(+x.saman || 0, +x.ot || 0, +x.yem || 0))), bw = (W - 20) / l.length;
  const r = (x, k, i, c) => { const h = (+x[k] || 0) / mx * (H - 26); return `<rect x="${10 + i * bw + k.length * 0 + ({ saman: 0, ot: 1, yem: 2 })[k] * bw / 3.4}" y="${H - 14 - h}" width="${bw / 3.6}" height="${h}" fill="${c}"/>`; };
  return `<h3>Son ${l.length} gün <span style="color:#eab308">■ saman</span> <span style="color:#22c55e">■ ot</span> <span style="color:#3b82f6">■ yem</span></h3><svg viewBox="0 0 ${W} ${H}" width="100%">${l.map((x, i) => r(x, "saman", i, "#eab308") + r(x, "ot", i, "#22c55e") + r(x, "yem", i, "#3b82f6")).join("")}
    <text x="10" y="${H - 2}">${trT(l[0].tarih)}</text><text x="${W - 70}" y="${H - 2}">${trT(l[l.length - 1].tarih)}</text></svg>`;
}
function yemFiyat(k) { return D.yemFiyat.filter(x => x.yem === k).sort((a, b) => b.tarih.localeCompare(a.tarih) || b.id.localeCompare(a.id))[0]; }
function borsaYem(k) {
  const kod = YEMLER[k].kod; if (!kod) return null;
  const x = (HUB || []).find(r => r.UrunKodu === kod) || (FIYAT && FIYAT.son && FIYAT.son[kod]);
  return x && (x.UrunKodu ? { tarih: x.Tarih, min: x.MinFiyat, max: x.MaxFiyat, ort: x.OrtFiyat } : x);
}
function mHesap() {
  const f = num(val("m_fiyat")), b = +val("m_birim"), kg = f / b;
  document.getElementById("m_sonuc").textContent = f ? `1 kg = ${fmt(kg, 2)} ₺ · 50 kg = ${fmt(kg * 50, 2)} ₺` : "";
}
function yemFiyatKaydet() {
  const f = num(val("m_fiyat")), tarih = val("m_tarih"); if (!f || !tarih) return toast("Fiyat ve tarih gerekli");
  D.yemFiyat.push({ id: uid(), yem: YEM, tarih, kg: f / +val("m_birim"), not: val("m_not") }); save();
}
function topluEkle() {
  const tur = val("tb_tur"), cins = val("tb_cins"); let n = 0, atla = 0;
  for (const satir of val("tb_liste").split("\n")) {
    const p = satir.trim().split(/\s+/); if (!p[0]) continue;
    if (D.hayvanlar.find(h => h.kupe === p[0])) { atla++; continue; }
    let dogum = ""; const t = p[1] || "";
    let m = t.match(/^(\d{1,2})[./-](\d{1,2})[./-](\d{4})$/);
    if (m) dogum = `${m[3]}-${m[2].padStart(2, "0")}-${m[1].padStart(2, "0")}`;
    else if (/^\d{4}$/.test(t)) dogum = t + "-01-01";
    else if (/^\d{4}-\d{2}-\d{2}$/.test(t)) dogum = t;
    D.hayvanlar.push({ id: uid(), kupe: p[0], ad: "", tur, cins, dogum, not: "", aktif: true }); n++;
  }
  if (!n) return toast(atla ? "Hepsi zaten kayıtlı" : "Küpe no girin");
  save(`${n} hayvan eklendi${atla ? `, ${atla} zaten vardı` : ""}`);
}
function menu(a) { document.getElementById("nav").classList.toggle("acik", a); document.getElementById("perde").classList.toggle("acik", a); }
function hesap() {
  const kg = num(val("h_kg")), x = birlesik()[val("h_urun")];
  document.getElementById("h_sonuc").textContent = kg && x ? `≈ ${fmt(kg * x.ort)} ₺  (${fmt(kg * x.min)} – ${fmt(kg * x.max)})` : "–";
}
async function fiyatYukle() {
  try { const r = await fetch("data/fiyat.json?t=" + Date.now()); if (r.ok) FIYAT = await r.json(); } catch (e) {}
  render();
  await Promise.all([fetch(API).then(r => r.json()).then(j => CANLI = j).catch(() => {}), fetch(API0).then(r => r.json()).then(j => HUB = j).catch(() => {})]);
  render();
}

/* ---------- Kaydetme işlemleri ---------- */
function upsert(list, rec) { const i = D[list].findIndex(x => x.id === rec.id); if (i >= 0) D[list][i] = rec; else D[list].push(rec); EDIT = null; }
function kuzuKaydet() {
  const anne = val("k_anne"), tarih = val("k_tarih"), sayi = num(val("k_sayi"));
  if (!anne || !tarih) return toast("Anne küpe no ve tarih gerekli");
  const e = num(val("k_erkek")), d = num(val("k_disi"));
  if (e + d > sayi) return toast("Erkek + dişi, kuzu sayısından fazla olamaz");
  upsert("kuzulama", { id: EDIT && EDIT.tip === "kuzulama" ? EDIT.id : uid(), anne, tarih, sayi, erkek: e, disi: d, olu: num(val("k_olu")), not: val("k_not") });
  save();
}
function katimKaydet() {
  const anne = val("c_anne"), tarih = val("c_tarih");
  if (!anne || !tarih) return toast("Anne küpe no ve tarih gerekli");
  D.katim.push({ id: uid(), anne, tarih }); save();
}
function asiKaydet() {
  const tarih = val("a_tarih"); if (!tarih) return toast("Tarih gerekli");
  upsert("asilar", { id: EDIT && EDIT.tip === "asilar" ? EDIT.id : uid(), tur: val("a_tur"), tarih, adet: num(val("a_adet")) || "", hedef: val("a_hedef"), not: val("a_not") });
  save();
}
function turKaydet() {
  const ad = val("t_ad"); if (!ad) return toast("Aşı adı gerekli");
  const hedef = val("t_hedef");
  upsert("asiTur", { id: EDIT && EDIT.tip === "asiTur" ? EDIT.id : uid(), ad, hedef, aralikGun: num(val("t_aralik")) || (hedef === "suru" ? 365 : 0), ilkGun: num(val("t_ilk")), rapelGun: num(val("t_rapel")), not: val("t_not") });
  save();
}
function yemKaydet() {
  const tarih = val("y_tarih"); if (!tarih) return toast("Tarih gerekli");
  const rec = { tarih, saman: num(val("y_saman")), ot: num(val("y_ot")), yem: num(val("y_yem")), not: val("y_not") };
  const i = D.tuketim.findIndex(x => x.tarih === tarih); if (i >= 0) D.tuketim[i] = rec; else D.tuketim.push(rec);
  EDIT = null; save();
}
function dunKopyala() {
  const t = val("y_tarih"), o = [...D.tuketim].filter(x => x.tarih < t).sort((a, b) => b.tarih.localeCompare(a.tarih))[0];
  if (!o) return toast("Önceki gün kaydı yok");
  for (const k of ["saman", "ot", "yem"]) document.getElementById("y_" + k).value = o[k] ?? "";
  toast(trT(o.tarih) + " değerleri getirildi – Kaydet'e basın");
}
function hayvanKaydet() {
  const kupe = val("h_kupe"); if (!kupe) return toast("Küpe no gerekli");
  const id = EDIT && EDIT.tip === "hayvanlar" ? EDIT.id : uid();
  if (D.hayvanlar.find(x => x.kupe === kupe && x.id !== id)) return toast("Bu küpe no zaten kayıtlı");
  upsert("hayvanlar", { id, kupe, ad: val("h_ad"), tur: val("h_tur"), cins: val("h_cins"), dogum: val("h_dogum"), not: val("h_not"), aktif: document.getElementById("h_aktif").checked });
  save();
}
function duzenle(tip, id) { EDIT = { tip, id }; render(); scrollTo(0, 0); }
function sil(list, id, k = "id") { if (!confirm("Bu kayıt silinsin mi?")) return; D[list] = D[list].filter(x => x[k] !== id); EDIT = null; save("Silindi"); }
function filtre(q, id) { q = q.toLocaleLowerCase("tr"); document.querySelectorAll(`#${id} tr`).forEach((r, i) => { if (i) r.style.display = r.textContent.toLocaleLowerCase("tr").includes(q) ? "" : "none"; }); }

/* ---------- Yedek ---------- */
function indir(ad, icerik, tip) { const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([icerik], { type: tip })); a.download = ad; a.click(); }
function yedekAl() { D.yedek = Date.now(); localStorage.setItem(KEY, JSON.stringify(D)); indir(`suru-yedek-${bugun()}.json`, JSON.stringify(D, null, 1), "application/json"); render(); }
function yedekYukle(f) {
  if (!f) return; const r = new FileReader();
  r.onload = () => { try { const d = JSON.parse(r.result); if (!d.kuzulama || !d.tuketim) throw 0; if (!confirm("Mevcut veriler yedekteki ile değiştirilsin mi?")) return; localStorage.setItem(KEY, JSON.stringify(d)); D = load(); save("Yedek yüklendi"); } catch (e) { toast("Geçersiz yedek dosyası"); } };
  r.readAsText(f);
}
function csvAl() {
  const c = s => `"${String(s ?? "").replace(/"/g, '""')}"`, L = [];
  L.push("KUZULAMA", "Tarih;Anne;Kuzu;Erkek;Dişi;Ölü;Not", ...D.kuzulama.map(x => [x.tarih, x.anne, x.sayi, x.erkek, x.disi, x.olu, x.not].map(c).join(";")), "");
  L.push("AŞILAR", "Tarih;Aşı;Kime;Adet;Not", ...D.asilar.map(x => [x.tarih, asiAd(x.tur), x.hedef, x.adet, x.not].map(c).join(";")), "");
  L.push("TÜKETİM", "Tarih;Saman (balya);Ot (balya);Yem (çuval);Not", ...D.tuketim.map(x => [x.tarih, x.saman, x.ot, x.yem, x.not].map(c).join(";")), "");
  L.push("HAYVANLAR", "Küpe;Ad;Tür;Cinsiyet;Doğum;Sürüde;Not", ...D.hayvanlar.map(x => [x.kupe, x.ad, x.tur, x.cins, x.dogum, x.aktif === false ? "Hayır" : "Evet", x.not].map(c).join(";")));
  indir(`suru-${bugun()}.csv`, "\ufeff" + L.join("\n"), "text/csv");
}

/* ---------- Genel ---------- */
function go(v) { V = v; EDIT = null; location.hash = v; menu(false); render(); scrollTo(0, 0); }
function render() {
  document.querySelectorAll("#nav button").forEach(b => b.classList.toggle("on", b.dataset.v === V));
  document.getElementById("baslik").textContent = BASLIK[V] || "Özet";
  document.getElementById("app").innerHTML = (VIEWS[V] || VIEWS.ozet)();
}
function bildirim() {
  if (!("Notification" in window) || Notification.permission !== "granted" || localStorage.getItem("suru_bildirim") === bugun()) return;
  const acil = asiPlani().filter(p => p.tarih && fark(p.tarih, bugun()) <= 0);
  if (!acil.length) return;
  localStorage.setItem("suru_bildirim", bugun());
  new Notification("Sürü Takip – aşı zamanı", { body: acil.map(p => p.tur.ad).join(", "), icon: "icon.svg" });
}
document.getElementById("menuBtn").onclick = () => menu(true);
document.getElementById("nav").onclick = e => { if (e.target.dataset.v) go(e.target.dataset.v); };
addEventListener("hashchange", () => { const v = location.hash.slice(1); if (v && v !== V) { V = v; EDIT = null; render(); } });
render(); fiyatYukle(); bildirim();
if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js");
