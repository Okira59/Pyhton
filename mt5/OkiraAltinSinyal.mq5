//+------------------------------------------------------------------+
//| OkiraAltinSinyal.mq5                                             |
//| Altın Sinyal botunun (bot.py) MT5 Expert Advisor sürümü.         |
//| AL : 15dk EMA(20/50) + Bollinger(20,2) + MACD DEMA(12,26,9)      |
//|      yukarı ve StochRSI(14,14,3,3) %K son 20 mumda 0,00'a değdi.  |
//| SAT: tersi (%K 100,00'e değdi).                                  |
//| Çıkış: zarar durdur, +TrailStart pip kârda iz süren stop,        |
//|        ters sinyalde kapat ve ters yönde aç. Sabit kâr al yok.   |
//+------------------------------------------------------------------+
#property copyright "Okira59"
#property version   "1.00"
#property description "XAUUSD 15dk: EMA + Bollinger + MACD DEMA + StochRSI 0/100, iz süren stop"

input double InpLots          = 0.01;   // Lot (çoğu aracı kurumda 0.01 lot = 1 pip başına $1)
input double InpSlPips        = 25;     // Zarar durdur (pip)
input double InpTrailStart    = 20;     // İz süren stop başlangıcı (pip kâr)
input double InpTrailGap      = 10;     // İz süren stop mesafesi (pip)
input double InpTrailStep     = 0.2;    // Stop en az bu kadar ilerleyince güncellenir (pip)
input double InpPipSize       = 1.0;    // 1 pip = fiyat birimi (altın: 1.0 = $1)
input int    InpStochLookback = 20;     // StochRSI 0/100 değme penceresi (15dk mum)
input int    InpBars          = 1500;   // Hesaplamada kullanılan 15dk mum sayısı
input bool   InpAllowBuy      = true;   // AL işlemleri açılsın
input bool   InpAllowSell     = true;   // SAT işlemleri açılsın
input bool   InpNotify        = true;   // MT5 mobil bildirimi gönder
input ulong  InpMagic         = 590059; // Magic number
input int    InpSlippage      = 30;     // İzin verilen kayma (point)

#define NA EMPTY_VALUE

datetime g_lastBar = 0;

ENUM_ORDER_TYPE_FILLING Filling()
  {
   long f = SymbolInfoInteger(_Symbol, SYMBOL_FILLING_MODE);
   if((f & SYMBOL_FILLING_FOK) == SYMBOL_FILLING_FOK) return ORDER_FILLING_FOK;
   if((f & SYMBOL_FILLING_IOC) == SYMBOL_FILLING_IOC) return ORDER_FILLING_IOC;
   return ORDER_FILLING_RETURN;
  }

bool Send(MqlTradeRequest &rq, MqlTradeResult &rs, string what)
  {
   ZeroMemory(rs);
   rq.magic     = InpMagic;
   rq.symbol    = _Symbol;
   rq.deviation = InpSlippage;
   if(rq.action == TRADE_ACTION_DEAL) rq.type_filling = Filling();
   if(OrderSend(rq, rs) && (rs.retcode == TRADE_RETCODE_DONE || rs.retcode == TRADE_RETCODE_PLACED))
      return true;
   Print(what, " hatası: ", rs.retcode, " ", rs.comment);
   return false;
  }

//--- göstergeler (pandas karşılıkları: ewm(adjust=False), rolling, std(ddof=0))
void Ema(const double &x[], int n, int p, double &out[])
  {
   ArrayResize(out, n);
   double a = 2.0 / (p + 1.0);
   out[0] = x[0];
   for(int i = 1; i < n; i++)
      out[i] = a * x[i] + (1.0 - a) * out[i - 1];
  }

void Dema(const double &x[], int n, int p, double &out[])
  {
   double e1[], e2[];
   Ema(x, n, p, e1);
   Ema(e1, n, p, e2);
   ArrayResize(out, n);
   for(int i = 0; i < n; i++)
      out[i] = 2.0 * e1[i] - e2[i];
  }

void Rsi(const double &c[], int n, int p, double &out[])
  {
   ArrayResize(out, n);
   out[0] = NA;
   double g = 0, l = 0, a = 1.0 / p;
   for(int i = 1; i < n; i++)
     {
      double d  = c[i] - c[i - 1];
      double gi = d > 0 ? d : 0;
      double li = d < 0 ? -d : 0;
      if(i == 1) { g = gi; l = li; }
      else       { g = a * gi + (1.0 - a) * g; l = a * li + (1.0 - a) * l; }
      if(l == 0) out[i] = (g == 0 ? NA : 100.0);
      else       out[i] = 100.0 - 100.0 / (1.0 + g / l);
     }
  }

void StochK(const double &c[], int n, int rp, int sp, int ks, double &k[])
  {
   double r[], raw[];
   Rsi(c, n, rp, r);
   ArrayResize(raw, n);
   ArrayResize(k, n);
   for(int i = 0; i < n; i++)
     {
      raw[i] = NA;
      if(i < sp - 1) continue;
      double lo = DBL_MAX, hi = -DBL_MAX;
      bool ok = true;
      for(int j = i - sp + 1; j <= i; j++)
        {
         if(r[j] == NA) { ok = false; break; }
         lo = MathMin(lo, r[j]);
         hi = MathMax(hi, r[j]);
        }
      if(ok && hi > lo) raw[i] = (r[i] - lo) / (hi - lo) * 100.0;
     }
   for(int i = 0; i < n; i++)
     {
      k[i] = NA;
      if(i < ks - 1) continue;
      double s = 0;
      bool ok = true;
      for(int j = i - ks + 1; j <= i; j++)
        {
         if(raw[j] == NA) { ok = false; break; }
         s += raw[j];
        }
      if(ok) k[i] = s / ks;
     }
  }

int Dir(bool bull, bool bear) { return (bull ? 1 : 0) - (bear ? 1 : 0); }

//--- i. mumdaki sinyal: +1 AL, -1 SAT, 0 yok
int SignalAt(int i, const double &c[], const double &ef[], const double &es[],
             const double &ml[], const double &ms[], const double &k[])
  {
   int bp = 20;
   if(i < bp - 1) return 0;
   double sum = 0, sq = 0;
   for(int j = i - bp + 1; j <= i; j++) sum += c[j];
   double mid = sum / bp;
   for(int j = i - bp + 1; j <= i; j++) sq += (c[j] - mid) * (c[j] - mid);
   double dev = MathSqrt(sq / bp);
   double up = mid + 2.0 * dev, lo = mid - 2.0 * dev, C = c[i];

   int e  = Dir(ef[i] > es[i] && C > ef[i], ef[i] < es[i] && C < ef[i]);
   int b  = Dir(C > mid && C < up, C < mid && C > lo);
   int m  = Dir(ml[i] > ms[i], ml[i] < ms[i]);
   int st = 0;
   for(int j = i; j > i - InpStochLookback && j >= 0; j--)
     {
      if(k[j] == NA) continue;
      if(k[j] < 0.005)    { st = 1;  break; }   // %K = 0,00
      if(k[j] >= 99.995)  { st = -1; break; }   // %K = 100,00
     }
   int t = e + b + m;
   if(t == 3 && st == 1)   return 1;
   if(t == -3 && st == -1) return -1;
   return 0;
  }

//--- pozisyon yardımcıları
int CurrentDir()
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong tk = PositionGetTicket(i);
      if(tk == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if((ulong)PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;
      return PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY ? 1 : -1;
     }
   return 0;
  }

void CloseAll()
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong tk = PositionGetTicket(i);
      if(tk == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if((ulong)PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;
      bool buy = PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY;
      MqlTradeRequest rq; MqlTradeResult rs;
      ZeroMemory(rq);
      rq.action   = TRADE_ACTION_DEAL;
      rq.position = tk;
      rq.volume   = PositionGetDouble(POSITION_VOLUME);
      rq.type     = buy ? ORDER_TYPE_SELL : ORDER_TYPE_BUY;
      rq.price    = buy ? SymbolInfoDouble(_Symbol, SYMBOL_BID) : SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      rq.comment  = "Ters sinyal";
      Send(rq, rs, "Kapatma");
     }
  }

void Notify(string msg)
  {
   Print(msg);
   if(InpNotify && TerminalInfoInteger(TERMINAL_NOTIFICATIONS_ENABLED))
      SendNotification(msg);
  }

void Open(int dir)
  {
   if((dir == 1 && !InpAllowBuy) || (dir == -1 && !InpAllowSell)) return;
   double price = dir == 1 ? SymbolInfoDouble(_Symbol, SYMBOL_ASK) : SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double sl = NormalizeDouble(price - dir * InpSlPips * InpPipSize, _Digits);
   MqlTradeRequest rq; MqlTradeResult rs;
   ZeroMemory(rq);
   rq.action  = TRADE_ACTION_DEAL;
   rq.volume  = InpLots;
   rq.type    = dir == 1 ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
   rq.price   = price;
   rq.sl      = sl;
   rq.comment = dir == 1 ? "Altin Sinyal AL" : "Altin Sinyal SAT";
   if(Send(rq, rs, "Açılış"))
      Notify(StringFormat("%s %s @ %s · Zarar durdur %s (-%g pip)", dir == 1 ? "AL" : "SAT", _Symbol,
                          DoubleToString(rs.price > 0 ? rs.price : price, _Digits), DoubleToString(sl, _Digits), InpSlPips));
  }

//--- iz süren stop: kâr >= TrailStart olunca stop = fiyat - TrailGap (yalnızca ileri)
void ManageTrailing()
  {
   double stops = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL) * _Point;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong tk = PositionGetTicket(i);
      if(tk == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if((ulong)PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;
      int    dir   = PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY ? 1 : -1;
      double open  = PositionGetDouble(POSITION_PRICE_OPEN);
      double sl    = PositionGetDouble(POSITION_SL);
      double price = dir == 1 ? SymbolInfoDouble(_Symbol, SYMBOL_BID) : SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      double pips  = dir * (price - open) / InpPipSize;
      if(pips < InpTrailStart) continue;
      double newSl = NormalizeDouble(open + dir * (pips - InpTrailGap) * InpPipSize, _Digits);
      if(dir * (price - newSl) < stops) continue;
      if(sl != 0 && dir * (newSl - sl) < InpTrailStep * InpPipSize) continue;
      bool first = (sl == 0 || dir * (sl - open) < 0);
      MqlTradeRequest rq; MqlTradeResult rs;
      ZeroMemory(rq);
      rq.action   = TRADE_ACTION_SLTP;
      rq.position = tk;
      rq.sl       = newSl;
      rq.tp       = PositionGetDouble(POSITION_TP);
      if(Send(rq, rs, "Stop güncelleme") && first)
         Notify(StringFormat("İz süren stop devrede: %s %s · kâr %+.1f pip · stop %s",
                             dir == 1 ? "AL" : "SAT", _Symbol, pips, DoubleToString(newSl, _Digits)));
     }
  }

//+------------------------------------------------------------------+
int OnInit()
  {
   if(StringFind(_Symbol, "XAU") < 0 && StringFind(_Symbol, "GOLD") < 0)
      Print("Uyarı: Bu EA altın (XAUUSD) için ayarlandı. Şu anki sembol: ", _Symbol);
   Print("Okira Altın Sinyal EA başladı · ", _Symbol, " · lot ", InpLots, " · stop ", InpSlPips,
         " pip · iz süren stop +", InpTrailStart, "/", InpTrailGap, " pip");
   return INIT_SUCCEEDED;
  }

void OnTick()
  {
   ManageTrailing();

   datetime bar = iTime(_Symbol, PERIOD_M15, 0);
   if(bar == 0 || bar == g_lastBar) return;

   double c[];
   int n = CopyClose(_Symbol, PERIOD_M15, 1, InpBars, c);   // kapanmış mumlar, c[0] en eski
   if(n < 300) return;                                      // geçmiş veri henüz yüklenmedi
   g_lastBar = bar;

   double ef[], es[], f[], s[], ml[], ms[], k[];
   Ema(c, n, 20, ef);
   Ema(c, n, 50, es);
   Dema(c, n, 12, f);
   Dema(c, n, 26, s);
   ArrayResize(ml, n);
   for(int i = 0; i < n; i++) ml[i] = f[i] - s[i];
   Dema(ml, n, 9, ms);
   StochK(c, n, 14, 14, 3, k);

   int now  = SignalAt(n - 1, c, ef, es, ml, ms, k);
   int prev = SignalAt(n - 2, c, ef, es, ml, ms, k);
   if(now == 0 || now == prev) return;                      // yalnızca yeni sinyal

   int cur = CurrentDir();
   if(cur == now) return;
   if(cur != 0)
     {
      Notify(StringFormat("Ters sinyal: %s işlemi kapatılıyor", cur == 1 ? "AL" : "SAT"));
      CloseAll();
     }
   Open(now);
  }

void OnTradeTransaction(const MqlTradeTransaction &tr, const MqlTradeRequest &rq, const MqlTradeResult &rs)
  {
   if(tr.type != TRADE_TRANSACTION_DEAL_ADD || !HistoryDealSelect(tr.deal)) return;
   if((ulong)HistoryDealGetInteger(tr.deal, DEAL_MAGIC) != InpMagic) return;
   if(HistoryDealGetString(tr.deal, DEAL_SYMBOL) != _Symbol) return;
   if(HistoryDealGetInteger(tr.deal, DEAL_ENTRY) != DEAL_ENTRY_OUT) return;
   double p = HistoryDealGetDouble(tr.deal, DEAL_PROFIT) + HistoryDealGetDouble(tr.deal, DEAL_SWAP)
              + HistoryDealGetDouble(tr.deal, DEAL_COMMISSION);
   string why = HistoryDealGetInteger(tr.deal, DEAL_REASON) == DEAL_REASON_SL ? "stop" : "ters sinyal / elle";
   Notify(StringFormat("İşlem kapandı (%s) @ %s · %+.2f %s", why,
                       DoubleToString(HistoryDealGetDouble(tr.deal, DEAL_PRICE), _Digits),
                       p, AccountInfoString(ACCOUNT_CURRENCY)));
  }
//+------------------------------------------------------------------+
