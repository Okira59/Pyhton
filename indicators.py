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


def _rma(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(alpha=1 / n, adjust=False).mean()


def _atr(h: pd.Series, l: pd.Series, c: pd.Series, n: int) -> pd.Series:
    pc = c.shift()
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return _rma(tr, n)


def _norm(s: pd.Series, window: int = 1000) -> pd.Series:
    lo, hi = s.rolling(window, min_periods=1).min(), s.rolling(window, min_periods=1).max()
    return (s - lo) / (hi - lo).clip(lower=1e-10)


def lorentzian(df: pd.DataFrame, neighbors: int = 8, window: int = 900, horizon: int = 4,
               regime_threshold: float = -0.1, kernel_h: int = 8, kernel_r: float = 8.0, kernel_x: int = 25):
    """TradingView "Machine Learning: Lorentzian Classification" (jdehorty) uyarlaması.

    Özellikler: RSI(14), WT(10,11), CCI(20), ADX(20), RSI(9). Her mumda son `window` mum içinde
    (her 4 mumda bir) Lorentzian mesafesine göre en yakın `neighbors` komşunun `horizon` mum sonraki
    yönleri toplanır. Volatilite + rejim filtresi geçerse yön güncellenir, yoksa önceki yön korunur.
    Dönüş: (yön +1/-1/0, tahmin toplamı, çekirdek regresyonu yükseliyor mu)."""
    import numpy as np
    c, h, l = df.Close, df.High, df.Low
    hlc3 = (h + l + c) / 3
    e1 = ema(hlc3, 10)
    ci = (hlc3 - e1) / (0.015 * ema((hlc3 - e1).abs(), 10))
    wt1 = ema(ci, 11)
    sma20 = c.rolling(20).mean()
    mad = c.rolling(20).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
    cci = (c - sma20) / (0.015 * mad)
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    up, dn = h.diff(), -l.diff()
    dmp = np.where((up > dn) & (up > 0), up, 0.0)
    dmm = np.where((dn > up) & (dn > 0), dn, 0.0)
    trs, dps, dms = (pd.Series(x, index=df.index).ewm(alpha=1 / 20, adjust=False).mean() for x in (tr, dmp, dmm))
    dip, dim = dps / trs * 100, dms / trs * 100
    adx = _rma((dip - dim).abs() / (dip + dim) * 100, 20)
    F = pd.concat([rsi(c, 14) / 100, _norm(wt1 - wt1.rolling(4).mean()), _norm(cci), adx / 100, rsi(c, 9) / 100],
                  axis=1).to_numpy()
    cv = c.to_numpy()
    n = len(cv)
    lab = np.zeros(n)
    lab[:-horizon] = np.sign(cv[horizon:] - cv[:-horizon])
    ok = ~np.isnan(F).any(axis=1)
    pred = np.zeros(n)
    for t in range(n):
        if not ok[t]:
            continue
        j0 = max(0, t - window)
        j0 += (-j0) % 4
        cand = np.arange(j0, t - horizon + 1, 4)
        cand = cand[ok[cand]]
        if len(cand) < neighbors:
            continue
        dist = np.log1p(np.abs(F[cand] - F[t])).sum(axis=1)
        pred[t] = lab[cand[np.argpartition(dist, neighbors - 1)[:neighbors]]].sum()
    vol_ok = (_atr(h, l, c, 1) > _atr(h, l, c, 10)).to_numpy()
    src = ((df.Open + h + l + c) / 4).to_numpy()
    rng = (h - l).to_numpy()
    v1 = v2 = 0.0
    klmf = np.zeros(n)
    for i in range(n):
        v1 = 0.2 * (src[i] - (src[i - 1] if i else src[i])) + 0.8 * v1
        v2 = 0.1 * rng[i] + 0.8 * v2
        om = abs(v1 / v2) if v2 else 0.0
        a = (-om ** 2 + np.sqrt(om ** 4 + 16 * om ** 2)) / 8
        klmf[i] = a * src[i] + (1 - a) * (klmf[i - 1] if i else src[i])
    slope = pd.Series(np.abs(np.diff(klmf, prepend=klmf[0])), index=df.index)
    avg = ema(slope, 200)
    regime_ok = ((slope - avg) / avg >= regime_threshold).to_numpy()
    sig = np.zeros(n)
    s = 0
    for i in range(n):
        if vol_ok[i] and regime_ok[i]:
            s = 1 if pred[i] > 0 else -1 if pred[i] < 0 else s
        sig[i] = s
    w = (1 + np.arange(kernel_x + 2) ** 2 / (2 * kernel_r * kernel_h ** 2)) ** -kernel_r
    yhat = c.rolling(len(w)).apply(lambda x: (x[::-1] * w).sum() / w.sum(), raw=True)
    return (pd.Series(sig, index=df.index), pd.Series(pred, index=df.index), yhat > yhat.shift())


def supertrend_ai(df: pd.DataFrame, length: int = 10, fmin: float = 1.0, fmax: float = 5.0, step: float = 0.5,
                  perf_alpha: float = 10, cluster: int = 2):
    """LuxAlgo "SuperTrend AI (Clustering)" uyarlaması: 1-5 arası çarpanlarla SuperTrend'ler, performanslarına
    göre k-means (3 küme) ile kümelenir; en iyi kümenin ortalama çarpanıyla SuperTrend çizilir.
    Dönüş: (yön +1/-1, SuperTrend çizgisi, seçilen çarpan)."""
    import numpy as np
    c, h, l = df.Close.to_numpy(), df.High.to_numpy(), df.Low.to_numpy()
    atr = _atr(df.High, df.Low, df.Close, length).to_numpy()
    hl2 = (h + l) / 2
    fac = np.arange(fmin, fmax + 1e-9, step)
    m, n = len(fac), len(c)
    upper, lower, out = np.full(m, hl2[0]), np.full(m, hl2[0]), np.full(m, hl2[0])
    trend, perf = np.zeros(m), np.zeros(m)
    k = 2 / (perf_alpha + 1)
    tf, up_, lo_, os_ = fmin, hl2[0], hl2[0], 0
    d_out, line, f_out = np.zeros(n), np.zeros(n), np.zeros(n)
    for i in range(n):
        if i and not np.isnan(atr[i]):
            perf += k * ((c[i] - c[i - 1]) * np.sign(c[i - 1] - out) - perf)
            up, dn = hl2[i] + atr[i] * fac, hl2[i] - atr[i] * fac
            upper = np.where(c[i - 1] < upper, np.minimum(up, upper), up)
            lower = np.where(c[i - 1] > lower, np.maximum(dn, lower), dn)
            trend = np.where(c[i] > upper, 1, np.where(c[i] < lower, 0, trend))
            out = np.where(trend == 1, lower, upper)
            p = sorted(perf.tolist())
            cen = [p[int(q)] + (q - int(q)) * (p[min(int(q) + 1, m - 1)] - p[int(q)]) for q in ((m - 1) * .25, (m - 1) * .5, (m - 1) * .75)]
            pl, fl = perf.tolist(), fac.tolist()
            for _ in range(100):
                groups = [[], [], []]
                for v, fv in zip(pl, fl):
                    a0, a1, a2 = abs(v - cen[0]), abs(v - cen[1]), abs(v - cen[2])
                    groups[0 if a0 <= a1 and a0 <= a2 else 1 if a1 <= a2 else 2].append((v, fv))
                new = [sum(g_[0] for g_ in g) / len(g) if g else cen[j] for j, g in enumerate(groups)]
                if new == cen:
                    break
                cen = new
            if groups[cluster]:
                tf = sum(g_[1] for g_ in groups[cluster]) / len(groups[cluster])
            u, d = hl2[i] + atr[i] * tf, hl2[i] - atr[i] * tf
            up_ = min(u, up_) if c[i - 1] < up_ else u
            lo_ = max(d, lo_) if c[i - 1] > lo_ else d
            os_ = 1 if c[i] > up_ else 0 if c[i] < lo_ else os_
        d_out[i], line[i], f_out[i] = (1 if os_ else -1), (lo_ if os_ else up_), tf
    ix = df.index
    return pd.Series(d_out, index=ix), pd.Series(line, index=ix), pd.Series(f_out, index=ix)
