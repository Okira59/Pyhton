//+------------------------------------------------------------------+
//| OkiraForex.mq5 - Sade Forex al-sat botu (MT5 Expert Advisor)      |
//| Yön: EMA 50/200 | Giriş: RSI 14 | SL/TP: ATR 14                   |
//| Günlük kâr kilidi: 100-200 USD, sadece elle tekrar başlar         |
//+------------------------------------------------------------------+
#property copyright "OkiRa"
#property version   "1.00"

#include <Trade\Trade.mqh>

//==================== AYARLAR (tek yer) ============================
input string          InpSymbols     = "EURUSD,GBPUSD,USDJPY,XAUUSD"; // Semboller: virgüllü liste | * = Piyasa Gözlemi | FOREX = kurumdaki tüm döviz+metal
input string          InpSuffix      = "";        // Kurum sembol eki (ör. .m, -pro). Yoksa boş
input ENUM_TIMEFRAMES InpTF          = PERIOD_H1; // Zaman dilimi
input double          InpLots        = 0.01;      // Lot (her işlem)
input int             InpEmaFast     = 50;        // Hızlı EMA
input int             InpEmaSlow     = 200;       // Yavaş EMA
input int             InpRsiPeriod   = 14;        // RSI periyodu
input double          InpRsiBuy      = 40;        // AL: yükseliş trendinde RSI bu seviyeyi yukarı keserse
input double          InpRsiSell     = 60;        // SAT: düşüş trendinde RSI bu seviyeyi aşağı keserse
input int             InpAtrPeriod   = 14;        // ATR periyodu
input double          InpSlAtr       = 1.5;       // Zarar durdur = ATR x bu
input double          InpTpAtr       = 3.0;       // Kâr al = ATR x bu
input int             InpMaxOpen     = 1;         // Aynı anda en fazla kaç işlem (tüm semboller toplamı). 1 = açık işlem kapanmadan yenisi açılmaz
input double          InpDailyMin    = 100;       // Günlük kâr kilidi ALT (USD): ulaşınca yeni işlem yok, sistem durur
input double          InpDailyMax    = 200;       // Günlük kâr kilidi ÜST (USD): açık işlemler toplam bu kâra ulaşınca kapanır
input ulong           InpMagic       = 590100;    // Magic number (diğer EA/elle işlemlerden ayırır)
input int             InpSlippage    = 30;        // İzin verilen kayma (point)
//===================================================================

CTrade   trade;
string   syms[];
int      hFast[], hSlow[], hRsi[], hAtr[];
datetime lastBar[];
string   gvLock, gvStart, gvLockStart, gvCloseAll;
const string BTN = "OkiraForexBtn";

//--- kilit durumu: 0 = çalışıyor, 1 = günlük hedef ile durdu, 2 = elle durduruldu
int      LockState()          { return GlobalVariableCheck(gvLock) ? (int)GlobalVariableGet(gvLock) : 0; }
datetime DayStart()           { return StringToTime(TimeToString(TimeTradeServer(), TIME_DATE)); }
datetime PeriodStart()
{
   if(LockState() == 1 && GlobalVariableCheck(gvLockStart)) return (datetime)GlobalVariableGet(gvLockStart);
   datetime s = GlobalVariableCheck(gvStart) ? (datetime)GlobalVariableGet(gvStart) : 0;
   datetime d = DayStart();
   return s > d ? s : d;
}

//--- sembol listesi
void AddSymbol(string s)
{
   StringTrimLeft(s); StringTrimRight(s);
   if(s == "") return;
   for(int i = 0; i < ArraySize(syms); i++) if(syms[i] == s) return;
   if(!SymbolSelect(s, true)) { PrintFormat("Sembol bulunamadı: %s", s); return; }
   int n = ArraySize(syms);
   ArrayResize(syms, n + 1);
   syms[n] = s;
}

bool IsForexOrMetal(string s)
{
   ENUM_SYMBOL_CALC_MODE m = (ENUM_SYMBOL_CALC_MODE)SymbolInfoInteger(s, SYMBOL_TRADE_CALC_MODE);
   if(m == SYMBOL_CALC_MODE_FOREX || m == SYMBOL_CALC_MODE_FOREX_NO_LEVERAGE) return true;
   string p = s; StringToUpper(p);
   return StringFind(p, "XAU") == 0 || StringFind(p, "XAG") == 0 || StringFind(p, "XPT") == 0 || StringFind(p, "XPD") == 0;
}

void BuildSymbols()
{
   ArrayResize(syms, 0);
   string list = InpSymbols; StringTrimLeft(list); StringTrimRight(list);
   string up = list; StringToUpper(up);
   if(list == "")                 AddSymbol(_Symbol);
   else if(list == "*")           { for(int i = 0; i < SymbolsTotal(true); i++)  AddSymbol(SymbolName(i, true)); }
   else if(up == "FOREX")         { for(int i = 0; i < SymbolsTotal(false); i++) { string s = SymbolName(i, false); if(IsForexOrMetal(s)) AddSymbol(s); } }
   else
   {
      string parts[];
      int n = StringSplit(list, ',', parts);
      for(int i = 0; i < n; i++) { StringTrimLeft(parts[i]); StringTrimRight(parts[i]); if(parts[i] != "") AddSymbol(parts[i] + InpSuffix); }
   }
}

//--- günlük kâr: kapanan işlemler + açık işlemlerin anlık kâr/zararı (sadece bu EA)
double ClosedProfit(datetime from)
{
   double sum = 0;
   if(!HistorySelect(from, TimeTradeServer() + 86400)) return 0;
   for(int i = HistoryDealsTotal() - 1; i >= 0; i--)
   {
      ulong d = HistoryDealGetTicket(i);
      if(HistoryDealGetInteger(d, DEAL_MAGIC) != (long)InpMagic) continue;
      if((datetime)HistoryDealGetInteger(d, DEAL_TIME) < from) continue;
      sum += HistoryDealGetDouble(d, DEAL_PROFIT) + HistoryDealGetDouble(d, DEAL_SWAP)
           + HistoryDealGetDouble(d, DEAL_COMMISSION) + HistoryDealGetDouble(d, DEAL_FEE);
   }
   return sum;
}

double OpenProfit(int &count)
{
   double sum = 0; count = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t == 0 || PositionGetInteger(POSITION_MAGIC) != (long)InpMagic) continue;
      sum += PositionGetDouble(POSITION_PROFIT) + PositionGetDouble(POSITION_SWAP);
      count++;
   }
   return sum;
}

void CloseAll(string why)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t == 0 || PositionGetInteger(POSITION_MAGIC) != (long)InpMagic) continue;
      trade.SetTypeFillingBySymbol(PositionGetString(POSITION_SYMBOL));
      if(!trade.PositionClose(t)) PrintFormat("Kapatılamadı #%I64u: %s", t, trade.ResultRetcodeDescription());
   }
   Print("Tüm işlemler kapatıldı: ", why);
}

bool HasPosition(string s)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t != 0 && PositionGetInteger(POSITION_MAGIC) == (long)InpMagic && PositionGetString(POSITION_SYMBOL) == s) return true;
   }
   return false;
}

int CountOpen()
{
   int n = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t != 0 && PositionGetInteger(POSITION_MAGIC) == (long)InpMagic) n++;
   }
   for(int i = OrdersTotal() - 1; i >= 0; i--)   // gönderilmiş ama henüz dolmamış emirler de sayılır
   {
      ulong o = OrderGetTicket(i);
      if(o != 0 && OrderGetInteger(ORDER_MAGIC) == (long)InpMagic) n++;
   }
   return n;
}

//--- kilit / manuel açılış
void Lock(int state, string why)
{
   if(state == 1) GlobalVariableSet(gvLockStart, (double)PeriodStart());
   GlobalVariableSet(gvLock, state);
   string msg = "OkiraForex DURDU: " + why + ". Tekrar açmak için grafikteki BAŞLAT düğmesine basın.";
   Print(msg);
   SendNotification(msg);
   UpdateButton();
}

void Unlock()
{
   GlobalVariableSet(gvLock, 0);
   GlobalVariableSet(gvStart, (double)TimeTradeServer());   // kâr sayacı bu andan itibaren sıfırdan başlar
   GlobalVariableDel(gvLockStart);
   GlobalVariableDel(gvCloseAll);
   Print("OkiraForex elle tekrar BAŞLATILDI.");
   UpdateButton();
}

void UpdateButton()
{
   bool on = LockState() == 0;
   if(ObjectFind(0, BTN) < 0)
   {
      ObjectCreate(0, BTN, OBJ_BUTTON, 0, 0, 0);
      ObjectSetInteger(0, BTN, OBJPROP_CORNER, CORNER_RIGHT_UPPER);
      ObjectSetInteger(0, BTN, OBJPROP_XDISTANCE, 170);
      ObjectSetInteger(0, BTN, OBJPROP_YDISTANCE, 30);
      ObjectSetInteger(0, BTN, OBJPROP_XSIZE, 160);
      ObjectSetInteger(0, BTN, OBJPROP_YSIZE, 36);
      ObjectSetInteger(0, BTN, OBJPROP_COLOR, clrWhite);
      ObjectSetInteger(0, BTN, OBJPROP_FONTSIZE, 11);
   }
   ObjectSetString(0, BTN, OBJPROP_TEXT, on ? "DURDUR" : "BAŞLAT");
   ObjectSetInteger(0, BTN, OBJPROP_BGCOLOR, on ? clrFireBrick : clrSeaGreen);
   ObjectSetInteger(0, BTN, OBJPROP_STATE, false);
   ChartRedraw();
}

void OnChartEvent(const int id, const long &lparam, const double &dparam, const string &sparam)
{
   if(id != CHARTEVENT_OBJECT_CLICK || sparam != BTN) return;
   if(LockState() == 0)
   {
      if(MessageBox("Sistem durdurulsun mu? (açık işlemler kapanmaz)", "OkiraForex", MB_YESNO | MB_ICONQUESTION) == IDYES)
         Lock(2, "elle durduruldu");
   }
   else if(MessageBox("Sistem tekrar başlatılsın mı? Günlük kâr sayacı sıfırdan başlar.", "OkiraForex", MB_YESNO | MB_ICONQUESTION) == IDYES)
      Unlock();
   UpdateButton();
}

//--- günlük kâr kilidi
void CheckDailyLock()
{
   int n = 0;
   datetime from = PeriodStart();
   double open = OpenProfit(n);
   double total = ClosedProfit(from) + open;
   int st = LockState();

   if(st == 0 && total >= InpDailyMin)
      Lock(1, StringFormat("günlük kâr %.2f USD, hedef %.0f-%.0f USD", total, InpDailyMin, InpDailyMax));

   if(LockState() == 1 && n > 0)
   {
      if(total >= InpDailyMax)      { GlobalVariableSet(gvCloseAll, 1); Print(StringFormat("Günlük kâr üst sınıra ulaştı (%.2f USD)", total)); }
      else if(total < InpDailyMin)  { GlobalVariableSet(gvCloseAll, 1); Print(StringFormat("Kâr %.0f USD altına düşmesin diye (%.2f USD)", InpDailyMin, total)); }
   }
   if(GlobalVariableCheck(gvCloseAll))   // karar verildiyse tüm pozisyonlar kapanana kadar dene
   {
      if(n > 0) CloseAll("günlük kâr kilidi");
      else      GlobalVariableDel(gvCloseAll);
   }

   st = LockState();
   string durum = st == 0 ? "ÇALIŞIYOR" : (st == 1 ? "DURDU (günlük hedef)" : "DURDU (elle)");
   Comment(StringFormat("OkiraForex | %s\nGünlük kâr: %.2f USD (kilit %.0f-%.0f)\nAçık işlem: %d | Sembol: %d | %s",
           durum, total, InpDailyMin, InpDailyMax, n, ArraySize(syms), EnumToString(InpTF)));
}

//--- sinyal ve işlem
bool Buf(int h, int shift, double &v) { double b[1]; if(CopyBuffer(h, 0, shift, 1, b) != 1) return false; v = b[0]; return true; }

bool CheckSymbol(int i)
{
   string s = syms[i];
   datetime bar = iTime(s, InpTF, 0);
   if(bar == 0 || bar == lastBar[i]) return false;

   double ef, es, r1, r2, atr;
   if(!Buf(hFast[i], 1, ef) || !Buf(hSlow[i], 1, es) || !Buf(hRsi[i], 1, r1) || !Buf(hRsi[i], 2, r2) || !Buf(hAtr[i], 1, atr)) return false;
   lastBar[i] = bar;   // sadece kapanmış mumda bir kez karar ver

   if(LockState() != 0 || CountOpen() >= InpMaxOpen || HasPosition(s) || atr <= 0) return false;
   bool hedging = AccountInfoInteger(ACCOUNT_MARGIN_MODE) == ACCOUNT_MARGIN_MODE_RETAIL_HEDGING;
   if(!hedging && PositionSelect(s)) return false;   // netting hesapta başka işlemin pozisyonunu değiştirmesin

   bool buy  = ef > es && r2 < InpRsiBuy  && r1 >= InpRsiBuy;
   bool sell = ef < es && r2 > InpRsiSell && r1 <= InpRsiSell;
   if(!buy && !sell) return false;

   int    dg   = (int)SymbolInfoInteger(s, SYMBOL_DIGITS);
   double pt   = SymbolInfoDouble(s, SYMBOL_POINT);
   double minD = (SymbolInfoInteger(s, SYMBOL_TRADE_STOPS_LEVEL) + 2) * pt;
   double sl   = MathMax(atr * InpSlAtr, minD);
   double tp   = MathMax(atr * InpTpAtr, minD);

   double step = SymbolInfoDouble(s, SYMBOL_VOLUME_STEP);
   int    vd   = step > 0 ? (int)MathMax(0.0, MathCeil(-MathLog10(step) - 1e-9)) : 2;
   double lots = MathMax(SymbolInfoDouble(s, SYMBOL_VOLUME_MIN), MathMin(SymbolInfoDouble(s, SYMBOL_VOLUME_MAX), MathRound(InpLots / step) * step));
   lots = NormalizeDouble(lots, vd);

   trade.SetTypeFillingBySymbol(s);
   bool ok;
   if(buy)
   {
      double p = SymbolInfoDouble(s, SYMBOL_ASK);
      ok = trade.Buy(lots, s, p, NormalizeDouble(p - sl, dg), NormalizeDouble(p + tp, dg), "OkiraForex AL");
   }
   else
   {
      double p = SymbolInfoDouble(s, SYMBOL_BID);
      ok = trade.Sell(lots, s, p, NormalizeDouble(p + sl, dg), NormalizeDouble(p - tp, dg), "OkiraForex SAT");
   }
   PrintFormat("%s %s %.2f lot | RSI %.1f | ATR %s | %s", buy ? "AL" : "SAT", s, lots, r1,
               DoubleToString(atr, dg), ok ? "açıldı" : trade.ResultRetcodeDescription());
   return ok;
}

//--- MT5 olayları
int OnInit()
{
   if(InpDailyMin <= 0 || InpDailyMax < InpDailyMin) { Print("Hata: InpDailyMax >= InpDailyMin > 0 olmalı"); return INIT_PARAMETERS_INCORRECT; }

   string key = StringFormat("OkiraForex_%I64d_%I64u_", AccountInfoInteger(ACCOUNT_LOGIN), InpMagic);
   gvLock = key + "kilit"; gvStart = key + "baslangic"; gvLockStart = key + "kilitbaslangic"; gvCloseAll = key + "hepsinikapat";
   if(!GlobalVariableCheck(gvStart)) GlobalVariableSet(gvStart, 0);

   trade.SetExpertMagicNumber(InpMagic);
   trade.SetDeviationInPoints(InpSlippage);

   BuildSymbols();
   int n = ArraySize(syms);
   if(n == 0) { Print("Hata: işlem yapılacak sembol yok"); return INIT_PARAMETERS_INCORRECT; }
   ArrayResize(hFast, n); ArrayResize(hSlow, n); ArrayResize(hRsi, n); ArrayResize(hAtr, n); ArrayResize(lastBar, n);
   for(int i = 0; i < n; i++)
   {
      hFast[i] = iMA(syms[i], InpTF, InpEmaFast, 0, MODE_EMA, PRICE_CLOSE);
      hSlow[i] = iMA(syms[i], InpTF, InpEmaSlow, 0, MODE_EMA, PRICE_CLOSE);
      hRsi[i]  = iRSI(syms[i], InpTF, InpRsiPeriod, PRICE_CLOSE);
      hAtr[i]  = iATR(syms[i], InpTF, InpAtrPeriod);
      lastBar[i] = iTime(syms[i], InpTF, 0);   // açılışta eski sinyale girmesin, yeni mumu beklesin
   }
   PrintFormat("OkiraForex başladı: %d sembol, %s. Durum: %s", n, EnumToString(InpTF), LockState() == 0 ? "ÇALIŞIYOR" : "DURDU (BAŞLAT düğmesini bekliyor)");
   UpdateButton();
   EventSetTimer(1);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   for(int i = 0; i < ArraySize(syms); i++) { IndicatorRelease(hFast[i]); IndicatorRelease(hSlow[i]); IndicatorRelease(hRsi[i]); IndicatorRelease(hAtr[i]); }
   ObjectDelete(0, BTN);
   Comment("");
}

void OnTimer()
{
   CheckDailyLock();
   for(int i = 0; i < ArraySize(syms); i++) CheckSymbol(i);
}

void OnTick() { OnTimer(); }
