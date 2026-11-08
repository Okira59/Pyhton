//+------------------------------------------------------------------+
//| OkiraDipTavan.mq5                                                |
//| Dip-Tavan botunun (dip_tavan.py) MT5 Expert Advisor sürümü.      |
//| 15dk, 30dk, 45dk, 1s: EMA(9/21), Bollinger(20,2), RSI(14),       |
//| StochRSI(14,14,3,3), MACD DEMA(12,26,9), Hacim - son 5 mumda     |
//| dip / tavan koşulları sayılır.                                   |
//| AL : 15dk'da StochRSI (%K tam 0,00) dahil en az 3/6 dip ve       |
//|      30dk/45dk/1s'den en az ikisinde en az 1 dip koşulu.         |
//| SAT: tersi (%K tam 100,00).                                      |
//| Çıkış: zarar durdur; +TrailStart pip kârda kademeli iz süren stop|
//|        (kâr arttıkça mesafe daralır); -LossStart pip zararda     |
//|        kademeli zarar koruma (dipten toparlanınca kapat, zarar   |
//|        derinleştikçe mesafe daralır); ters sinyalde çevir.       |
//+------------------------------------------------------------------+
#property copyright "Okira59"
#property version   "1.10"
#property description "XAUUSD Dip-Tavan: 15dk/30dk/45dk/1s, StochRSI 0/100 şartı, kademeli iz süren stop ve zarar koruma"

input double InpLots          = 0.01;   // Lot (çoğu aracı kurumda 0.01 lot = 1 pip başına $1)
input double InpSlPips        = 25;     // Zarar durdur (pip)
input double InpTrailStart    = 20;     // İz süren stop başlangıcı (pip kâr)
input double InpTrailGap      = 15;     // Başlangıçtaki iz süren stop mesafesi (pip)
input double InpTrailShrink   = 0.5;    // Kâr 1 pip arttıkça mesafe bu kadar daralır
input double InpTrailMin      = 3;      // En dar iz süren stop mesafesi (pip)
input double InpLossStart     = 15;     // Zarar koruma başlangıcı (pip zarar)
input double InpLossGap       = 15;     // Dipten bu kadar toparlanınca kapat (pip)
input double InpLossShrink    = 0.5;    // Zarar 1 pip derinleştikçe mesafe bu kadar daralır
input double InpLossMin       = 5;      // En dar zarar koruma mesafesi (pip)
input double InpTrailStep     = 0.2;    // Stop en az bu kadar ilerleyince güncellenir (pip)
input double InpPipSize       = 1.0;    // 1 pip = fiyat birimi (altın: 1.0 = $1)
input int    InpLookback      = 5;      // Dip/tavan koşulları son kaç mumda aranır
input int    InpMinScore15    = 3;      // 15dk'da en az kaç koşul (StochRSI dahil)
input int    InpMinScoreHigh  = 1;      // 30dk/45dk/1s'den en az ikisinde en az kaç koşul
input int    InpBars          = 3000;   // Hesaplamada kullanılan 15dk mum sayısı
input bool   InpAllowBuy      = true;   // AL işlemleri açılsın
input bool   InpAllowSell     = true;   // SAT işlemleri açılsın
input bool   InpNotify        = true;   // MT5 mobil bildirimi gönder
input ulong  InpMagic         = 590060; // Magic number
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

void StochK(const double &r[], int n, int sp, int ks, double &k[])
  {
   double raw[];
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

void Sma(const double &x[], int n, int p, double &out[])
  {
   ArrayResize(out, n);
   double s = 0;
   for(int i = 0; i < n; i++)
     {
      s += x[i];
      if(i >= p) s -= x[i - p];
      out[i] = i >= p - 1 ? s / p : NA;
     }
  }

//--- her mum için dip / tavan koşul sayısı (0-6) ve StochRSI koşulu
void Scores(const double &h[], const double &l[], const double &c[], const double &v[], int n,
            int &dipN[], int &topN[], bool &dipSt[], bool &topSt[])
  {
   int w = InpLookback;
   double ef[], es[], mid[], r[], k[], f[], s[], ml[], ms[], vm[];
   Ema(c, n, 9, ef);
   Ema(c, n, 21, es);
   Sma(c, n, 20, mid);
   Rsi(c, n, 14, r);
   StochK(r, n, 14, 3, k);
   Dema(c, n, 12, f);
   Dema(c, n, 26, s);
   ArrayResize(ml, n);
   for(int i = 0; i < n; i++) ml[i] = f[i] - s[i];
   Dema(ml, n, 9, ms);
   Sma(v, n, 20, vm);
   double up[], lo[];
   ArrayResize(up, n);
   ArrayResize(lo, n);
   for(int i = 0; i < n; i++)
     {
      up[i] = NA; lo[i] = NA;
      if(mid[i] == NA) continue;
      double sq = 0;
      for(int j = i - 19; j <= i; j++) sq += (c[j] - mid[i]) * (c[j] - mid[i]);
      double dev = MathSqrt(sq / 20.0);
      up[i] = mid[i] + 2.0 * dev;
      lo[i] = mid[i] - 2.0 * dev;
     }
   ArrayResize(dipN, n); ArrayResize(topN, n); ArrayResize(dipSt, n); ArrayResize(topSt, n);
   for(int i = 0; i < n; i++)
     {
      bool bbD = false, bbT = false, stD = false, stT = false, vol = false, rOk = (i >= w - 1);
      double rMin = DBL_MAX, rMax = -DBL_MAX;
      if(i >= w - 1)
         for(int j = i - w + 1; j <= i; j++)
           {
            if(lo[j] != NA && l[j] <= lo[j]) bbD = true;
            if(up[j] != NA && h[j] >= up[j]) bbT = true;
            if(k[j] != NA && k[j] < 0.005)   stD = true;   // %K = 0,00
            if(k[j] != NA && k[j] >= 99.995) stT = true;   // %K = 100,00
            if(vm[j] != NA && v[j] > 1.5 * vm[j]) vol = true;
            if(r[j] == NA) rOk = false;
            else { rMin = MathMin(rMin, r[j]); rMax = MathMax(rMax, r[j]); }
           }
      bool rUp = i >= 1 && r[i] != NA && r[i - 1] != NA && r[i] > r[i - 1];
      bool rDn = i >= 1 && r[i] != NA && r[i - 1] != NA && r[i] < r[i - 1];
      double hi = ml[i] - ms[i], hp = i >= 1 ? ml[i - 1] - ms[i - 1] : 0;
      bool mD = i >= 1 && hi < 0 && hi > hp;
      bool mT = i >= 1 && hi > 0 && hi < hp;
      bool eD = c[i] > ef[i] && ef[i] < es[i];
      bool eT = c[i] < ef[i] && ef[i] > es[i];
      dipN[i] = (int)bbD + (int)(rOk && rMin < 35 && rUp) + (int)stD + (int)mD + (int)eD + (int)vol;
      topN[i] = (int)bbT + (int)(rOk && rMax > 65 && rDn) + (int)stT + (int)mT + (int)eT + (int)vol;
      dipSt[i] = stD;
      topSt[i] = stT;
     }
  }

//--- 15dk mumlarından üst zaman dilimi (gün başına hizalı, UTC) üretir
int Resample(const MqlRates &rt[], const long &utc[], int n, int minutes,
             double &h[], double &l[], double &c[], double &v[], long &closeT[])
  {
   long sec = minutes * 60, cur = -1;
   int m = -1;
   ArrayResize(h, n); ArrayResize(l, n); ArrayResize(c, n); ArrayResize(v, n); ArrayResize(closeT, n);
   for(int i = 0; i < n; i++)
     {
      long day = utc[i] - utc[i] % 86400;
      long b = day + ((utc[i] - day) / sec) * sec;
      if(b != cur)
        {
         m++; cur = b;
         h[m] = rt[i].high; l[m] = rt[i].low; v[m] = 0; closeT[m] = b + sec;
        }
      h[m] = MathMax(h[m], rt[i].high);
      l[m] = MathMin(l[m], rt[i].low);
      c[m] = rt[i].close;
      v[m] += (double)rt[i].tick_volume;
     }
   return m + 1;
  }

//--- kapanmış 15dk mumlarda sinyal dizisi (+1 dip/AL, -1 tavan/SAT, 0 yok)
bool Signals(int &sig[], int &n15, string &info)
  {
   MqlRates rt[];
   ArraySetAsSeries(rt, false);
   int n = CopyRates(_Symbol, PERIOD_M15, 1, InpBars, rt);   // kapanmış mumlar, rt[0] en eski
   if(n < 500) return false;
   long off = (long)(TimeTradeServer() - TimeGMT());
   off = (long)MathRound(off / 900.0) * 900;                // sunucu saati - UTC
   long utc[];
   ArrayResize(utc, n);
   double h[], l[], c[], v[];
   ArrayResize(h, n); ArrayResize(l, n); ArrayResize(c, n); ArrayResize(v, n);
   for(int i = 0; i < n; i++)
     {
      utc[i] = (long)rt[i].time - off;
      h[i] = rt[i].high; l[i] = rt[i].low; c[i] = rt[i].close; v[i] = (double)rt[i].tick_volume;
     }
   int dN[], tN[];
   bool dS[], tS[];
   Scores(h, l, c, v, n, dN, tN, dS, tS);

   int okD[], okT[], have[];
   ArrayResize(okD, n); ArrayResize(okT, n); ArrayResize(have, n);
   ArrayInitialize(okD, 0); ArrayInitialize(okT, 0); ArrayInitialize(have, 0);
   int mins[3] = {30, 45, 60};
   for(int f = 0; f < 3; f++)
     {
      double H[], L[], C[], V[];
      long ct[];
      int m = Resample(rt, utc, n, mins[f], H, L, C, V, ct);
      int a[], b[];
      bool x[], y[];
      Scores(H, L, C, V, m, a, b, x, y);
      int p = -1;
      for(int i = 0; i < n; i++)
        {
         long T = utc[i] + 900;                              // 15dk mumun kapanışı
         while(p + 1 < m && ct[p + 1] <= T) p++;            // yalnızca kapanmış üst mum
         if(p < 0) continue;
         have[i]++;
         if(a[p] >= InpMinScoreHigh) okD[i]++;
         if(b[p] >= InpMinScoreHigh) okT[i]++;
        }
     }
   ArrayResize(sig, n);
   for(int i = 0; i < n; i++)
     {
      bool dip = have[i] == 3 && dN[i] >= InpMinScore15 && dS[i] && okD[i] >= 2;
      bool top = have[i] == 3 && tN[i] >= InpMinScore15 && tS[i] && okT[i] >= 2;
      sig[i] = (dip ? 1 : 0) - (top ? 1 : 0);
     }
   n15 = n;
   info = StringFormat("15dk dip %d/6 tavan %d/6", dN[n - 1], tN[n - 1]);
   return true;
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

void Open(int dir, string info)
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
   rq.comment = dir == 1 ? "Dip-Tavan AL" : "Dip-Tavan SAT";
   if(Send(rq, rs, "Açılış"))
      Notify(StringFormat("Dip-Tavan %s %s @ %s · Zarar durdur %s (-%g pip) · %s", dir == 1 ? "DİP AL" : "TAVAN SAT",
                          _Symbol, DoubleToString(rs.price > 0 ? rs.price : price, _Digits),
                          DoubleToString(sl, _Digits), InpSlPips, info));
  }

//--- pozisyonun en derin zararı (pip); EA yeniden başlasa da kaybolmasın diye global değişkende
string TroughKey(ulong tk) { return StringFormat("OkiraDT_%I64u_tr", tk); }

void ClosePos(ulong tk, int dir, string why)
  {
   MqlTradeRequest rq; MqlTradeResult rs;
   ZeroMemory(rq);
   rq.action   = TRADE_ACTION_DEAL;
   rq.position = tk;
   rq.volume   = PositionGetDouble(POSITION_VOLUME);
   rq.type     = dir == 1 ? ORDER_TYPE_SELL : ORDER_TYPE_BUY;
   rq.price    = dir == 1 ? SymbolInfoDouble(_Symbol, SYMBOL_BID) : SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   rq.comment  = why;
   Send(rq, rs, why);
  }

//--- kademeli çıkış:
//    kâr >= TrailStart: stop = zirve - max(TrailMin, TrailGap - TrailShrink*(zirve-TrailStart)) (yalnızca ileri)
//    kâr < TrailStart ve dip zarar >= LossStart: fiyat dip + max(LossMin, LossGap - LossShrink*(dip-LossStart))
//    seviyesine dönerse kapat (seviye yalnızca aşağı iner)
void ManageExits()
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
      double tp    = PositionGetDouble(POSITION_TP);
      double price = dir == 1 ? SymbolInfoDouble(_Symbol, SYMBOL_BID) : SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      double pips  = dir * (price - open) / InpPipSize;
      double slPips = sl == 0 ? -InpSlPips : dir * (sl - open) / InpPipSize;
      bool   trailing = slPips >= 0;

      string key = TroughKey(tk);
      double tr = GlobalVariableCheck(key) ? GlobalVariableGet(key) : 0;
      if(-pips > tr) { tr = -pips; GlobalVariableSet(key, tr); }

      if(pips >= InpTrailStart || trailing)
        {
         if(tp != 0)                                          // zarar koruma seviyesini kaldır
           {
            MqlTradeRequest rq; MqlTradeResult rs;
            ZeroMemory(rq);
            rq.action = TRADE_ACTION_SLTP; rq.position = tk; rq.sl = sl; rq.tp = 0;
            Send(rq, rs, "Zarar koruma kaldırma");
            tp = 0;
           }
         if(pips < InpTrailStart) continue;
         double gap   = MathMax(InpTrailMin, InpTrailGap - InpTrailShrink * (pips - InpTrailStart));
         double newSl = NormalizeDouble(open + dir * (pips - gap) * InpPipSize, _Digits);
         if(dir * (price - newSl) < stops) continue;
         if(sl != 0 && dir * (newSl - sl) < InpTrailStep * InpPipSize) continue;
         bool first = !trailing;
         MqlTradeRequest rq; MqlTradeResult rs;
         ZeroMemory(rq);
         rq.action   = TRADE_ACTION_SLTP;
         rq.position = tk;
         rq.sl       = newSl;
         rq.tp       = 0;
         if(Send(rq, rs, "Stop güncelleme") && first)
            Notify(StringFormat("Dip-Tavan iz süren stop devrede: %s %s · kâr %+.1f pip · stop %s",
                                dir == 1 ? "AL" : "SAT", _Symbol, pips, DoubleToString(newSl, _Digits)));
         continue;
        }

      if(tr < InpLossStart) continue;
      double lgap  = MathMax(InpLossMin, InpLossGap - InpLossShrink * (tr - InpLossStart));
      double level = NormalizeDouble(open + dir * (-tr + lgap) * InpPipSize, _Digits);
      if(tp != 0 && dir * (level - tp) > 0) level = tp;      // seviye yalnızca aşağı iner
      if(dir * (price - level) >= 0)                          // fiyat seviyeye döndü
        {
         Notify(StringFormat("Dip-Tavan zarar koruma: %s %s kapatılıyor · dip -%.1f pip · %+.1f pip",
                             dir == 1 ? "AL" : "SAT", _Symbol, tr, pips));
         ClosePos(tk, dir, "Zarar koruma");
         continue;
        }
      if(tp != 0 && MathAbs(level - tp) < InpTrailStep * InpPipSize) continue;
      if(dir * (level - price) < stops) continue;
      bool first = (tp == 0);
      MqlTradeRequest rq; MqlTradeResult rs;
      ZeroMemory(rq);
      rq.action   = TRADE_ACTION_SLTP;                        // seviye kâr al emri olarak sunucuya da konur
      rq.position = tk;
      rq.sl       = sl;
      rq.tp       = level;
      if(Send(rq, rs, "Zarar koruma") && first)
         Notify(StringFormat("Dip-Tavan zarar koruma devrede: %s %s · dip -%.1f pip · fiyat %s seviyesine dönerse kapanır",
                             dir == 1 ? "AL" : "SAT", _Symbol, tr, DoubleToString(level, _Digits)));
     }
  }

//+------------------------------------------------------------------+
int OnInit()
  {
   if(StringFind(_Symbol, "XAU") < 0 && StringFind(_Symbol, "GOLD") < 0)
      Print("Uyarı: Bu EA altın (XAUUSD) için ayarlandı. Şu anki sembol: ", _Symbol);
   Print("Okira Dip-Tavan EA başladı · ", _Symbol, " · lot ", InpLots, " · stop ", InpSlPips,
         " pip · iz süren stop +", InpTrailStart, "/", InpTrailGap, "→", InpTrailMin,
         " pip · zarar koruma -", InpLossStart, "/", InpLossGap, "→", InpLossMin, " pip");
   return INIT_SUCCEEDED;
  }

void OnTick()
  {
   ManageExits();

   datetime bar = iTime(_Symbol, PERIOD_M15, 0);
   if(bar == 0 || bar == g_lastBar) return;

   int sig[], n = 0;
   string info;
   if(!Signals(sig, n, info)) return;                       // geçmiş veri henüz yüklenmedi
   g_lastBar = bar;

   int now = sig[n - 1], prev = sig[n - 2];
   if(now == 0 || now == prev) return;                      // yalnızca yeni sinyal

   int cur = CurrentDir();
   if(cur == now) return;
   if(cur != 0)
     {
      Notify(StringFormat("Dip-Tavan ters sinyal: %s işlemi kapatılıyor", cur == 1 ? "AL" : "SAT"));
      CloseAll();
     }
   Open(now, info);
  }

void OnTradeTransaction(const MqlTradeTransaction &tr, const MqlTradeRequest &rq, const MqlTradeResult &rs)
  {
   if(tr.type != TRADE_TRANSACTION_DEAL_ADD || !HistoryDealSelect(tr.deal)) return;
   if((ulong)HistoryDealGetInteger(tr.deal, DEAL_MAGIC) != InpMagic) return;
   if(HistoryDealGetString(tr.deal, DEAL_SYMBOL) != _Symbol) return;
   if(HistoryDealGetInteger(tr.deal, DEAL_ENTRY) != DEAL_ENTRY_OUT) return;
   double p = HistoryDealGetDouble(tr.deal, DEAL_PROFIT) + HistoryDealGetDouble(tr.deal, DEAL_SWAP)
              + HistoryDealGetDouble(tr.deal, DEAL_COMMISSION);
   long rsn = HistoryDealGetInteger(tr.deal, DEAL_REASON);
   string why = rsn == DEAL_REASON_SL ? "stop" : rsn == DEAL_REASON_TP ? "zarar koruma" : "ters sinyal / zarar koruma / elle";
   ulong pid = (ulong)HistoryDealGetInteger(tr.deal, DEAL_POSITION_ID);
   if(!PositionSelectByTicket(pid)) GlobalVariableDel(TroughKey(pid));
   Notify(StringFormat("Dip-Tavan işlem kapandı (%s) @ %s · %+.2f %s", why,
                       DoubleToString(HistoryDealGetDouble(tr.deal, DEAL_PRICE), _Digits),
                       p, AccountInfoString(ACCOUNT_CURRENCY)));
  }
//+------------------------------------------------------------------+
