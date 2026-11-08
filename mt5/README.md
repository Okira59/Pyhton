# Okira Dip-Tavan – MT5 Expert Advisor

`OkiraDipTavan.mq5`, Telegram'daki Dip-Tavan botuyla (`dip_tavan.py`) aynı kuralla MT5'te otomatik işlem açar.

- **Göstergeler (her zaman diliminde, son 5 mum):** EMA(9/21), Bollinger(20,2), RSI(14), StochRSI(14,14,3,3), MACD DEMA(12,26,9), hacim (tick hacmi > 20 mum ortalamasının 1,5 katı).
- **AL (dip):** 15dk'da StochRSI %K tam 0,00 dahil en az 3/6 dip koşulu; 30dk, 45dk ve 1s'ten en az ikisinde en az 1 dip koşulu.
- **SAT (tavan):** tersi; %K tam 100,00.
- **Çıkış:** zarar durdur 25 pip; ters sinyalde kapat ve ters yönde aç. Sabit kâr al yok.
  - **Kademeli iz süren stop:** kâr +20 pip olunca stop 15 pip geriden başlar; kâr her 2 pip arttıkça mesafe 1 pip daralır (en az 3). +30'da 10, +40'ta 5 pip geriden.
  - **Kademeli zarar koruma:** zarar -15 pip olunca fiyat dipten 15 pip toparlanırsa işlem kapanır; zarar her 2 pip derinleştikçe bu mesafe 1 pip daralır (en az 5). Dip -20 ise -7,5'te, dip -24 ise -13,5'te çıkılır. Seviye pozisyona kâr al (TP) olarak da yazılır.
- Karar kapanmış 15dk mumda verilir; EA hangi zaman diliminde açılırsa açılsın 15dk veriyi kullanır. 30dk/45dk/1s mumları 15dk mumlarından UTC gün başına hizalanarak üretilir (Telegram botuyla aynı).

## Kurulum

1. MT5 → **Dosya → Veri Klasörünü Aç** → `MQL5\Experts` klasörüne `OkiraDipTavan.ex5` dosyasını kopyalayın (çalışmazsa `.mq5` dosyasını kopyalayıp **Derle** deyin).
2. **Gezgin** (Ctrl+N) penceresinde *Expert Advisors* üzerine sağ tıklayıp **Yenile** deyin.
3. Üst menüde **Algo Trading** düğmesini açın (yeşil).
4. XAUUSD grafiğini açın, EA'ya çift tıklayın. **Ortak** sekmesinde *Algo Trading'e izin ver* işaretli olsun; **Girdiler** sekmesinde ayarları kontrol edin.
5. Grafiğin sağ üstünde EA adı ve mavi şapka simgesi görünmeli. Mesajlar **Araç Kutusu → Uzmanlar** sekmesine yazılır.

Bilgisayar/MT5 kapalıyken EA çalışmaz; 7/24 için VPS (ör. MT5 içindeki MQL5 VPS) gerekir.

## Ayarlar

| Ayar | Varsayılan | Açıklama |
|---|---|---|
| InpLots | 0.01 | Lot. Çoğu kurumda 0.01 lot XAUUSD = 1 pip ($1 hareket) başına ~$1 |
| InpSlPips | 25 | Zarar durdur (pip) |
| InpTrailStart / InpTrailGap | 20 / 15 | İz süren stop başlangıcı / ilk mesafesi (pip) |
| InpTrailShrink / InpTrailMin | 0.5 / 3 | Kâr 1 pip arttıkça mesafenin daralması / en dar mesafe |
| InpLossStart / InpLossGap | 15 / 15 | Zarar koruma başlangıcı / dipten toparlanma mesafesi (pip) |
| InpLossShrink / InpLossMin | 0.5 / 5 | Zarar 1 pip derinleştikçe mesafenin daralması / en dar mesafe |
| InpPipSize | 1.0 | 1 pip = 1.0 fiyat ($1). Sembol ölçeği farklıysa değiştirin |
| InpLookback | 5 | Dip/tavan koşullarının arandığı mum sayısı |
| InpMinScore15 / InpMinScoreHigh | 3 / 1 | 15dk ve üst zaman dilimleri için en az koşul sayısı |
| InpAllowBuy / InpAllowSell | true | Yön kapatma |
| InpNotify | true | MT5 mobil bildirimi (Araçlar → Seçenekler → Bildirimler'de MetaQuotes ID gerekir) |
| InpMagic | 590060 | Diğer EA/elle işlemlerden ayırmak için |

Hacim koşulu kurumun tick hacmini kullanır; Telegram botu Bitget hacmini kullandığı için sinyaller zaman zaman farklı olabilir.
Sembol adı kurumunuzda farklı olabilir (XAUUSD.m, GOLD vb.); EA açıldığı grafiğin sembolünde işlem yapar.
Önce **demo hesapta** deneyin. Geçmiş test sonucu gelecekteki kârı garanti etmez.
