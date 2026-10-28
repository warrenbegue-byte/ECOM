"""Stratégies inspirées des reels.

Chaque stratégie expose :
  reset()            -> remet à zéro l'état (compteurs de trades par jour)
  prepare(df)        -> calcule les indicateurs (sans regarder le futur)
  signal(i, pos)     -> Signal | None, évalué à la clôture de la bougie i
                        pos = +1 / -1 / 0 (position actuelle)
  manage(i, side, entry, stop, risk) -> nouveau stop | None   (optionnel)
Le même objet sert au backtest et au bot live MT5.
Dans les paramètres, 0 veut dire « désactivé » (rr=0 : pas d'objectif, sortie en fin de séance).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .backtest import Signal


def _hhmm(s: str) -> int:
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def _bar_minutes(df: pd.DataFrame) -> int:
    return int(pd.Series(df.index).diff().median() / pd.Timedelta(minutes=1)) if len(df) > 1 else 5


class ORBStrategy:
    """ORB NY — Opening Range Breakout sur la session de New York (reel @protos_quant).

    1. Range = plus haut / plus bas des `range_minutes` premières minutes après `session_open` (NY).
    2. Entrée :
       - entry="breakout" : première clôture au-delà du range ;
       - entry="candle"   : dans le sens de la bougie d'ouverture, dès la fin du range
         (version étudiée par Zarattini & Aziz, 2023, sur QQQ).
    3. Stop : autre côté du range ("range"), milieu ("mid") ou stop_atr x ATR journalier ("atr").
    4. Objectif rr x risque, ou rr=0 : on laisse courir jusqu'à `flat_time`.
    Filtres : taille du range en ATR journalier, tendance (veille / moyenne 20 jours), sens.
    """
    name = "orb"

    def __init__(self, range_minutes: int = 15, session_open: str = "09:30", last_entry: str = "11:30",
                 flat_time: str = "15:50", entry: str = "breakout", rr: float = 2.0, stop_mode: str = "range",
                 stop_atr: float = 0.1, atr_days: int = 14, min_range_atr: float = 0.0, max_range_atr: float = 0.0,
                 trend: str = "none", direction: str = "both", max_trades_per_day: int = 1,
                 tz: str = "America/New_York"):
        self.range_minutes, self.entry, self.rr, self.stop_mode = range_minutes, entry, rr, stop_mode
        self.open_m, self.last_m, self.flat_m = _hhmm(session_open), _hhmm(last_entry), _hhmm(flat_time)
        self.stop_atr, self.atr_days = stop_atr, atr_days
        self.min_range_atr, self.max_range_atr = min_range_atr, max_range_atr
        self.trend, self.direction, self.max_trades, self.tz = trend, direction, max_trades_per_day, tz
        self.reset()

    def reset(self):
        self.count: dict = {}

    def prepare(self, df: pd.DataFrame):
        local = df.index.tz_convert(self.tz)
        self.dates = np.asarray(local.date)
        self.minutes = np.asarray(local.hour * 60 + local.minute)
        self.bar = _bar_minutes(df)
        self.range_end = self.open_m + self.range_minutes
        in_range = (self.minutes >= self.open_m) & (self.minutes < self.range_end)
        day = self.dates
        # valeurs de la journée, lues uniquement APRÈS la fin du range -> pas de biais futur
        self.rh = df["high"].where(in_range).groupby(day).transform("max").to_numpy()
        self.rl = df["low"].where(in_range).groupby(day).transform("min").to_numpy()
        self.ro = df["open"].where(in_range).groupby(day).transform("first").to_numpy()
        self.close = df["close"].to_numpy()

        # séance (ouverture -> sortie) agrégée par jour : ATR et tendance journaliers de la VEILLE
        sess = (self.minutes >= self.open_m) & (self.minutes < self.flat_m)
        s = df[sess]
        daily = pd.DataFrame({"h": s["high"].groupby(day[sess]).max(), "l": s["low"].groupby(day[sess]).min(),
                              "c": s["close"].groupby(day[sess]).last()})
        prev_c = daily["c"].shift(1)
        tr = pd.concat([daily["h"] - daily["l"], (daily["h"] - prev_c).abs(), (daily["l"] - prev_c).abs()], axis=1).max(axis=1)
        daily["atr"] = tr.rolling(self.atr_days, min_periods=3).mean().shift(1)
        daily["prev_c"] = prev_c
        daily["sma"] = daily["c"].rolling(20, min_periods=10).mean().shift(1)
        m = pd.Series(day).map
        self.atr = m(daily["atr"]).to_numpy(dtype=float)
        self.prev_c = m(daily["prev_c"]).to_numpy(dtype=float)
        self.sma = m(daily["sma"]).to_numpy(dtype=float)

    def _allowed(self, side: int, i: int) -> bool:
        if (self.direction == "long" and side < 0) or (self.direction == "short" and side > 0):
            return False
        ref = {"prev_close": self.prev_c[i], "sma20": self.sma[i]}.get(self.trend)
        if ref is None:
            return True
        return not np.isnan(ref) and (self.close[i] - ref) * side > 0

    def signal(self, i: int, pos: int) -> Signal | None:
        m, d = self.minutes[i], self.dates[i]
        if pos:
            return Signal(0) if m >= self.flat_m else None
        if self.count.get(d, 0) >= self.max_trades or m >= self.last_m:
            return None
        rh, rl, c, atr = self.rh[i], self.rl[i], self.close[i], self.atr[i]
        if np.isnan(rh) or np.isnan(rl):
            return None
        if self.entry == "candle":
            # la bougie qui termine le range vient de clôturer
            if not (m < self.range_end <= m + self.bar):
                return None
            side = int(np.sign(c - self.ro[i]))
        else:
            if m < self.range_end:
                return None
            side = 1 if c > rh else (-1 if c < rl else 0)
        if side == 0 or not self._allowed(side, i):
            return None
        width = rh - rl
        if self.min_range_atr or self.max_range_atr or self.stop_mode == "atr":
            if np.isnan(atr) or atr <= 0:
                return None
            if (self.min_range_atr and width < self.min_range_atr * atr) or \
               (self.max_range_atr and width > self.max_range_atr * atr):
                return None
        if self.stop_mode == "atr":
            stop = c - side * self.stop_atr * atr
        elif self.stop_mode == "mid":
            stop = (rh + rl) / 2
        else:
            stop = rl if side > 0 else rh
        self.count[d] = self.count.get(d, 0) + 1
        return Signal(side, stop=stop, rr=self.rr or None)


class GoldBreakoutStrategy:
    """XAUUSD — cassure Donchian dans le sens de la tendance (reel @shahmeer___ahmed).

    Ce n'est PAS du HFT : le vrai HFT demande colocation et microsecondes, impossible
    depuis un PC perso chez un broker CFD. C'est un bot intraday qui tourne en local.

    - Tendance : EMA rapide > EMA lente (achats) ou < (ventes) ; direction="long" pour n'acheter que.
    - Entrée : clôture au-delà du plus haut/bas des `donchian` dernières bougies.
    - Stop = atr_mult x ATR, objectif = rr x risque (rr=0 : pas d'objectif).
    - trail_atr > 0 : stop suiveur à trail_atr x ATR ; breakeven_r > 0 : stop au prix d'entrée
      dès que le gain latent atteint breakeven_r x R.
    - Fenêtre en heures UTC, sortie en fin de fenêtre (0-24 = 24h/24, on garde la nuit).
    """
    name = "gold"

    def __init__(self, ema_fast: int = 50, ema_slow: int = 200, donchian: int = 20, atr_len: int = 14,
                 atr_mult: float = 1.5, rr: float = 1.5, trail_atr: float = 0.0, breakeven_r: float = 0.0,
                 start_hour_utc: int = 7, end_hour_utc: int = 20, direction: str = "both",
                 max_trades_per_day: int = 3):
        self.ema_fast, self.ema_slow, self.donchian = ema_fast, ema_slow, donchian
        self.atr_len, self.atr_mult, self.rr = atr_len, atr_mult, rr
        self.trail_atr, self.breakeven_r = trail_atr, breakeven_r
        self.start_h, self.end_h, self.direction = start_hour_utc, end_hour_utc, direction
        self.max_trades = max_trades_per_day
        self.reset()

    def reset(self):
        self.count: dict = {}

    def prepare(self, df: pd.DataFrame):
        c = df["close"]
        self.ef = c.ewm(span=self.ema_fast, adjust=False).mean().to_numpy()
        self.es = c.ewm(span=self.ema_slow, adjust=False).mean().to_numpy()
        prev_c = c.shift(1)
        tr = pd.concat([df["high"] - df["low"], (df["high"] - prev_c).abs(), (df["low"] - prev_c).abs()], axis=1).max(axis=1)
        self.atr = tr.ewm(alpha=1 / self.atr_len, adjust=False).mean().to_numpy()
        self.dch = df["high"].rolling(self.donchian).max().shift(1).to_numpy()
        self.dcl = df["low"].rolling(self.donchian).min().shift(1).to_numpy()
        self.close = c.to_numpy()
        utc = df.index.tz_convert("UTC")
        self.hours = np.asarray(utc.hour)
        self.dates = np.asarray(utc.date)
        self.warmup = max(self.ema_slow, self.donchian, self.atr_len)

    def signal(self, i: int, pos: int) -> Signal | None:
        h, d = self.hours[i], self.dates[i]
        if pos:
            return Signal(0) if self.end_h < 24 and h >= self.end_h else None
        if i < self.warmup or not (self.start_h <= h < self.end_h) or self.count.get(d, 0) >= self.max_trades:
            return None
        c, atr = self.close[i], self.atr[i]
        side = 0
        if self.ef[i] > self.es[i] and c > self.dch[i]:
            side = 1
        elif self.ef[i] < self.es[i] and c < self.dcl[i]:
            side = -1
        if side == 0 or (self.direction == "long" and side < 0) or (self.direction == "short" and side > 0):
            return None
        self.count[d] = self.count.get(d, 0) + 1
        return Signal(side, stop=c - side * self.atr_mult * atr, rr=self.rr or None)

    def manage(self, i: int, side: int, entry: float, stop: float, risk: float) -> float | None:
        c, best = self.close[i], stop
        if self.breakeven_r and (c - entry) * side >= self.breakeven_r * risk:
            best = entry if (entry - best) * side > 0 else best
        if self.trail_atr:
            trail = c - side * self.trail_atr * self.atr[i]
            best = trail if (trail - best) * side > 0 else best
        return best if best != stop else None


STRATEGIES = {"orb": ORBStrategy, "gold": GoldBreakoutStrategy}
