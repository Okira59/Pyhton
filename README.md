# Altın (XAU/USD) AL/SAT Sinyal Botu

15 dakikalık ve 4 saatlik grafiklerde **Bollinger Bantları, EMA, MACD ve StochRSI** göstergelerini izler.
8 kontrolün (4 gösterge × 2 zaman dilimi) **hepsi aynı yönü** gösterdiğinde sinyal üretir.

| Gösterge | AL (yükseliş) koşulu | SAT (düşüş) koşulu |
|---|---|---|
| EMA (20/50) | EMA20 > EMA50 ve fiyat > EMA20 | EMA20 < EMA50 ve fiyat < EMA20 |
| Bollinger (20, 2) | Fiyat orta bandın üstünde, üst bandın altında | Fiyat orta bandın altında, alt bandın üstünde |
| MACD (12/26/9) | MACD > sinyal çizgisi | MACD < sinyal çizgisi |
| StochRSI (14/14/3/3) | %K > %D ve %K < 80 | %K < %D ve %K > 20 |

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

## Notlar
- Veri kaynağı Yahoo Finance `GC=F` (altın vadeli). Fiyatı brokerınızdaki XAU/USD spot fiyatından birkaç dolar farklı olabilir, ancak göstergelerin yönü pratikte aynıdır.
- Yahoo 4s veri sunmadığı için 4s mumlar 1s veriden (UTC 00/04/08/12/16/20) oluşturulur.
- Bu bot yatırım tavsiyesi değildir; gerçek hesapta kullanmadan önce demo hesapta test edin.
