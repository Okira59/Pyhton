import pandas as pd


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def dema(series: pd.Series, period: int) -> pd.Series:
    e1 = ema(series, period)
    return 2 * e1 - ema(e1, period)


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss
    return 100 - 100 / (1 + rs)


def bollinger(close: pd.Series, period: int = 20, std: float = 2.0):
    mid = close.rolling(period).mean()
    dev = close.rolling(period).std(ddof=0)
    return mid + std * dev, mid, mid - std * dev


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    line = ema(close, fast) - ema(close, slow)
    sig = ema(line, signal)
    return line, sig, line - sig


def macd_dema(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    """TradingView "MACD DEMA": hızlı/yavaş ortalamalar ve sinyal çizgisi EMA yerine DEMA."""
    line = dema(close, fast) - dema(close, slow)
    sig = dema(line, signal)
    return line, sig, line - sig


def stoch_rsi(close: pd.Series, rsi_period: int = 14, stoch_period: int = 14,
              k_smooth: int = 3, d_smooth: int = 3):
    r = rsi(close, rsi_period)
    lo = r.rolling(stoch_period).min()
    hi = r.rolling(stoch_period).max()
    stoch = (r - lo) / (hi - lo) * 100
    k = stoch.rolling(k_smooth).mean()
    d = k.rolling(d_smooth).mean()
    return k, d


STOCH_BUY, STOCH_SELL = 0.0, 100.0  # StochRSI %K tam 0,00 -> AL, tam 100,00 -> SAT


def stoch_buy(k: pd.Series) -> pd.Series:
    return k.round(2) <= STOCH_BUY


def stoch_sell(k: pd.Series) -> pd.Series:
    return k.round(2) >= STOCH_SELL
