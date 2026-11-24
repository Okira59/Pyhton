# OkiraForex – Sade Forex al-sat botu (MT5)

`OkiraForex.mq5`: tek dosya, tüm ayarlar dosyanın en üstünde (MT5'te **Girdiler** sekmesi).

## Kural
- **Yön:** EMA50 > EMA200 → sadece AL; EMA50 < EMA200 → sadece SAT.
- **Giriş:** AL = RSI(14) 30'u aşağıdan yukarı keser; SAT = RSI(14) 70'i yukarıdan aşağı keser.
- **Çıkış:** Zarar durdur = ATR(14) × 1,5; Kâr al = ATR(14) × 3.
- Karar sadece kapanmış mumda verilir.
- **Varsayılan:** sadece XAUUSD (altın), 4 saatlik (H4), 0,05 lot. Geriye dönük testte en sağlam sonuç bu ayarla çıktı; döviz paritelerinde bu kurallar zarar etti.
- **Aynı anda tek işlem** (`InpMaxOpen` = 1): bir işlem açıkken başka sembolde sinyal gelse bile yeni işlem açılmaz; açık işlem kapanınca sıradaki sinyal beklenir.
- **Lot uyarısı:** 0,05 lot altında 1 USD fiyat hareketi = 5 USD. Pariteleri seçerseniz 0,05 lot EURUSD'de 1 pip = 0,5 USD olur; günlük 100 USD hedefe nadiren ulaşılır.

## Semboller
| `InpSymbols` | Anlamı |
|---|---|
| `XAUUSD` (varsayılan) | Sadece altın |
| `EURUSD,GBPUSD,XAUUSD` | Sadece bu liste |
| `*` | MT5 **Piyasa Gözlemi**'ndeki tüm semboller |
| `FOREX` | Kurumdaki tüm döviz pariteleri (majör, çapraz, egzotik) + XAU/XAG/XPT/XPD |
| boş | EA'nın açıldığı grafiğin sembolü |

Kurum sembolleri ek alıyorsa (`EURUSD.m`) `InpSuffix` = `.m` yazın.

## Günlük kâr kilidi (100–200 USD)
- Günlük kâr (bugün kapanan işlemler + açık işlemler, sadece bu EA) **100 USD**'ye ulaşınca sistem **DURUR**: yeni işlem açılmaz.
- Açık işlem kaldıysa: toplam **200 USD**'ye çıkınca hepsi kapanır; geri düşüp 100 USD'nin altına inerse yine hepsi kapanır (kazanç korunur).
- Hepsini tam 100'de kapatmak isterseniz `InpDailyMax` = `100` yapın.
- Hesap para birimi USD olmalı (değilse tutarlar hesap para biriminde sayılır).

## Manuel açılış
- Durduktan sonra **kendiliğinden başlamaz**: ertesi gün, MT5 yeniden açılsa, bilgisayar yeniden başlasa bile kapalı kalır.
- Tekrar açmak için grafiğin sağ üstündeki yeşil **BAŞLAT** düğmesine basıp **Evet** deyin. Kâr sayacı o andan itibaren sıfırdan başlar.
- Çalışırken kırmızı **DURDUR** düğmesiyle elle de durdurabilirsiniz (açık işlemler kapanmaz).
- Durum, günlük kâr ve açık işlem sayısı grafiğin sol üstünde yazar.

## Kurulum
1. MT5 → **Dosya → Veri Klasörünü Aç** → `MQL5\Experts` klasörüne `OkiraForex.ex5` dosyasını kopyalayın (ya da `.mq5`'i kopyalayıp MetaEditor'de açıp **Derle**).
2. **Gezgin** (Ctrl+N) → *Expert Advisors* → sağ tık → **Yenile**.
3. Üst menüde **Algo Trading** düğmesini açın (yeşil).
4. Herhangi bir grafiği açın (ör. EURUSD H1), `OkiraForex`'e çift tıklayın.
5. **Ortak** sekmesi: *Algo Trading'e izin ver* işaretli. **Girdiler** sekmesi: semboller, lot, hedefler.
6. **Tamam**. Grafikte DURDUR düğmesi ve sol üstte "ÇALIŞIYOR" görünür. Mesajlar **Araç Kutusu → Uzmanlar** sekmesinde.

MT5 kapalıyken bot çalışmaz; 7/24 için VPS gerekir. Önce **demo hesapta** deneyin; kâr garantisi yoktur.
