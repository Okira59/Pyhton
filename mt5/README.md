# Okira Altın Sinyal – MT5 Expert Advisor

`OkiraAltinSinyal.mq5`, Telegram'daki Altın Sinyal botuyla (`bot.py`) aynı kuralla MT5'te otomatik işlem açar.

- **AL:** 15dk EMA(20/50), Bollinger(20,2) ve MACD DEMA(12,26,9) yukarı; StochRSI(14,14,3,3) %K son 20 mumda 0,00'a değdi.
- **SAT:** tersi; %K 100,00'e değdi.
- **Çıkış:** zarar durdur 25 pip, kâr +20 pip olunca iz süren stop (10 pip geriden), ters sinyalde kapat ve ters yönde aç.
- Karar kapanmış 15dk mumda verilir; EA hangi zaman diliminde açılırsa açılsın 15dk veriyi kullanır.

## Kurulum

1. MT5 → **Dosya → Veri Klasörünü Aç** → `MQL5\Experts` klasörüne `OkiraAltinSinyal.mq5` dosyasını kopyalayın.
2. MT5'te **Gezgin** penceresinde *Expert Advisors* üzerine sağ tıklayıp **Yenile** deyin.
3. Dosyaya sağ tıklayıp **Düzenle** deyin; MetaEditor'da **Derle (F7)**. "0 errors" görmelisiniz.
4. Üst menüde **Algo Trading** düğmesini açın (yeşil).
5. XAUUSD grafiğini açın, EA'yı grafiğe sürükleyin. **Ortak** sekmesinde *Algo Trading'e izin ver* işaretli olsun; **Girdiler** sekmesinde ayarları kontrol edin.
6. Grafiğin sağ üstünde EA adı ve mavi şapka simgesi görünmeli. Mesajlar **Araç Kutusu → Uzmanlar** sekmesine yazılır.

Bilgisayar/MT5 kapalıyken EA çalışmaz; 7/24 için VPS (ör. MT5 içindeki MQL5 VPS) gerekir.

## Ayarlar

| Ayar | Varsayılan | Açıklama |
|---|---|---|
| InpLots | 0.01 | Lot. Çoğu kurumda 0.01 lot XAUUSD = 1 pip ($1 hareket) başına ~$1 |
| InpSlPips | 25 | Zarar durdur (pip) |
| InpTrailStart / InpTrailGap | 20 / 10 | İz süren stop başlangıcı / mesafesi (pip) |
| InpPipSize | 1.0 | 1 pip = 1.0 fiyat ($1). Sembol ölçeği farklıysa değiştirin |
| InpAllowBuy / InpAllowSell | true | Yön kapatma |
| InpNotify | true | MT5 mobil bildirimi (Araçlar → Seçenekler → Bildirimler'de MetaQuotes ID gerekir) |
| InpMagic | 590059 | Diğer EA/elle işlemlerden ayırmak için |

Sembol adı kurumunuzda farklı olabilir (XAUUSD.m, GOLD vb.); EA açıldığı grafiğin sembolünde işlem yapar.
Önce **demo hesapta** deneyin. Geçmiş test sonucu gelecekteki kârı garanti etmez.
