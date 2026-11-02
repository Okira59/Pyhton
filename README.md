# Altın (XAU/USD) AL/SAT Sinyal Botu

15 dakikalık ve 4 saatlik grafiklerde **Bollinger Bantları, EMA, MACD ve StochRSI** göstergelerini izler.
8 kontrolün (4 gösterge × 2 zaman dilimi) **hepsi aynı yönü** gösterdiğinde sinyal üretir.

| Gösterge | AL (yükseliş) koşulu | SAT (düşüş) koşulu |
|---|---|---|
| EMA (20/50) | EMA20 > EMA50 ve fiyat > EMA20 | EMA20 < EMA50 ve fiyat < EMA20 |
| Bollinger (20, 2) | Fiyat orta bandın üstünde, üst bandın altında | Fiyat orta bandın altında, alt bandın üstünde |
| MACD (12/26/9) | MACD > sinyal çizgisi | MACD < sinyal çizgisi |
| StochRSI (14/14/3/3) | %K > %D ve %K < 80 | %K < %D ve %K > 20 |

**Kâr al (KAPAT) sinyali:** Bir AL/SAT sinyalinden sonra fiyat giriş fiyatından `TP_PIPS` (varsayılan 20) pip kâra ulaşınca
"İŞLEMİ KAPAT" bildirimi gönderilir. Altında 1 pip = `PIP_SIZE` = 1 $ kabul edilir (20 pip = 20 $).
Değiştirmek için `bot.py` içindeki ayarları ya da `TP_PIPS` / `PIP_SIZE` ortam değişkenlerini kullanın.
Yeni bir sinyal gelirse açık işlemin yerini alır.

Yalnızca **kapanmış mumlar** kullanılır (repaint yok). Parametreler `bot.py` başındaki AYARLAR bölümünden değiştirilebilir.

## Kurulum
```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Kullanım
```bash
python bot.py             # Şu anki durumu bir kez kontrol et
python bot.py --loop      # Sürekli çalış, her 15dk mum kapanışında kontrol et
python bot.py --history   # Son 60 günde oluşan sinyalleri listele
```

### Telegram bildirimi (isteğe bağlı)
```bash
export TELEGRAM_BOT_TOKEN="123:ABC..."
export TELEGRAM_CHAT_ID="123456789"
python bot.py --loop
```
`--loop` modunda yalnızca **yeni** oluşan sinyaller gönderilir.

## 7/24 çalıştırma (GitHub Actions)
`.github/workflows/sinyal.yml` her 15 dakikada bir `python bot.py --notify` çalıştırır ve yeni sinyalleri Telegram'a gönderir.
Gerekenler (Repo → Settings → Secrets and variables → Actions):
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

Elle tetiklemek için: Actions → "Altin Sinyal Botu" → Run workflow.
GitHub zamanlanmış işleri bazen birkaç dakika gecikmeli çalıştırabilir.

## Notlar
- Veri kaynağı Bitget TradFi `XAUUSD` (MT5, bid fiyatı; Bitget'in herkese açık web grafiği uç noktası `v1/kline/getMoreKlineDataV2`). TradFi hacim vermediği için Dip-Tavan botunun hacim göstergesi Bitget vadeli `XAUUSDT` hacmini kullanır. Forex kapalıyken (Cuma 21:00 - Pazar 22:00 UTC) mum kullanılmaz. Alternatifler: `DATA_SOURCE=bitget` (XAUUSDT vadeli) veya `DATA_SOURCE=yahoo` (GC=F).
- 4s mumlar 1s veriden (UTC 00/04/08/12/16/20) oluşturulur.
- Bu bot yatırım tavsiyesi değildir; gerçek hesapta kullanmadan önce demo hesapta test edin.

## İkinci bot: Dip-Tavan (dip_tavan.py)
15dk, 30dk, 45dk ve 1s grafiklerde EMA(9/21), Bollinger(20,2), RSI(14), StochRSI(14,14,3,3), MACD(12,26,9) ve Hacim(20)
ile dip (🟢 AL) ve tavan (🔴 SAT) arar. Sinyal için: 15dk'da 6 koşuldan en az 4'ü, 30dk/45dk/1s'den en az ikisinde en az 2 koşul.
İşlem +20 pip ($20) kâra ulaşınca, -15 pip ($15) zarara ulaşınca (zarar durdur) ya da ters sinyal gelince kapanır;
kapanış mesajında kâr/zarar yüzdesi yazar. Ayarlar: `TP_PIPS`, `SL_PIPS`, `PIP_SIZE`.
```bash
python dip_tavan.py            # son durum
python dip_tavan.py --history  # son 60 günün sinyalleri + kâr/zarar özeti
```
GitHub Actions: `.github/workflows/dip_tavan.yml`, secret `TELEGRAM_BOT_TOKEN_15` (chat ID: `TELEGRAM_CHAT_ID_15`, yoksa `TELEGRAM_CHAT_ID`).

## Web paneli

İki botun durumu (fiyat grafiği, gösterge tabloları, açık işlem, son 60 günün sinyalleri ve kâr/zarar yüzdeleri)
`docs/index.html` sayfasında gösterilir: https://okira59.github.io/Pyhton/ (Altın Sinyal) ve https://okira59.github.io/Pyhton/dip-tavan.html (Dip-Tavan)

Botlar her çalışmada `docs/data/sinyal.json` ve `docs/data/dip_tavan.json` dosyalarını günceller; sayfa her dakika yenilenir.

## Saatlik durum mesajı

İki bot da her saatin ilk kontrolünde, sinyal olmasa bile Telegram'a 🕐 SAATLİK DURUM mesajı gönderir
(fiyat, gösterge tablosu, açık işlemin anlık kâr/zarar yüzdesi). Piyasa kapalıyken gönderilmez.
