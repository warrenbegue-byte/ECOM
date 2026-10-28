"""Stratégies inspirées des reels.

Chaque stratégie expose :
  reset()            -> remet à zéro l'état (compteurs de trades par jour)
  prepare(df)        -> calcule les indicateurs (sans regarder le futur)
  signal(i, pos)     -> Signal | None, évalué à la clôture de la bougie i
                        pos = +1 / -1 / 0 (position actuelle)
Le même objet sert au backtest et au bot live MT5.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .backtest import Signal


def _hhmm(s: str) -> int:
    h, m = s.split(":")
    return int(h) * 60 + int(m)


class ORBStrategy:
    """ORB NY — Opening Range Breakout sur la session de New York (reel @protos_quant).

    1. On mesure le plus haut / plus bas des `range_minutes` premières minutes après 9h30 (NY).
    2. Première clôture au-dessus du range -> achat ; en dessous -> vente.
    3. Stop de l'autre côté du range (ou au milieu, stop_mode="mid"), objectif = rr x risque.
    4. Pas de nouvelle entrée après `last_entry`, tout est clôturé à `flat_time`.
    Marchés adaptés : NQ/MNQ, ES/MES, QQQ, SPY (et XAUUSD qui bouge fort à l'ouverture US).
    """
    name = "orb"

    def __init__(self, range_minutes: int = 15, session_open: str = "09:30", last_entry: str = "11:30",
                 flat_time: str = "15:50", rr: float = 2.0, stop_mode: str = "range",
                 max_trades_per_day: int = 1, tz: str = "America/New_York"):
        self.range_minutes, self.rr, self.stop_mode = range_minutes, rr, stop_mode
        self.open_m, self.last_m, self.flat_m = _hhmm(session_open), _hhmm(last_entry), _hhmm(flat_time)
        self.max_trades, self.tz = max_trades_per_day, tz
        self.reset()

    def reset(self):
        self.count: dict = {}

    def prepare(self, df: pd.DataFrame):
        local = df.index.tz_convert(self.tz)
        self.dates = np.asarray(local.date)
        self.minutes = np.asarray(local.hour * 60 + local.minute)
        self.range_end = self.open_m + self.range_minutes
        in_range = (self.minutes >= self.open_m) & (self.minutes < self.range_end)
        g = pd.Series(self.dates, index=df.index)
        # valeur du range de la journée, lue uniquement APRÈS la fin du range -> pas de biais futur
        self.rh = df["high"].where(in_range).groupby(g.values).transform("max").to_numpy()
        self.rl = df["low"].where(in_range).groupby(g.values).transform("min").to_numpy()
        self.close = df["close"].to_numpy()

    def signal(self, i: int, pos: int) -> Signal | None:
        m, d = self.minutes[i], self.dates[i]
        if pos:
            return Signal(0) if m >= self.flat_m else None
        if not (self.range_end <= m < self.last_m) or self.count.get(d, 0) >= self.max_trades:
            return None
        rh, rl, c = self.rh[i], self.rl[i], self.close[i]
        if np.isnan(rh) or np.isnan(rl):
            return None
        mid = (rh + rl) / 2
        if c > rh:
            self.count[d] = self.count.get(d, 0) + 1
            return Signal(+1, stop=rl if self.stop_mode == "range" else mid, rr=self.rr)
        if c < rl:
            self.count[d] = self.count.get(d, 0) + 1
            return Signal(-1, stop=rh if self.stop_mode == "range" else mid, rr=self.rr)
        return None


class GoldBreakoutStrategy:
    """XAUUSD — cassure Donchian dans le sens de la tendance (reel @shahmeer___ahmed).

    Ce n'est PAS du HFT : le vrai HFT demande colocation et microsecondes, impossible
    depuis un PC perso chez un broker CFD. C'est un bot intraday M1/M5 qui tourne en
    local, ce qui correspond à ce que montre réellement ce type de reel.

    - Tendance : EMA rapide > EMA lente (achats) ou < (ventes).
    - Entrée : clôture au-delà du plus haut/bas des `donchian` dernières bougies.
    - Stop = atr_mult x ATR, objectif = rr x risque.
    - Fenêtre de trading en heures UTC (Londres + New York par défaut), sortie en fin de fenêtre.
    """
    name = "gold"

    def __init__(self, ema_fast: int = 50, ema_slow: int = 200, donchian: int = 20, atr_len: int = 14,
                 atr_mult: float = 1.5, rr: float = 1.5, start_hour_utc: int = 7, end_hour_utc: int = 20,
                 max_trades_per_day: int = 3):
        self.ema_fast, self.ema_slow, self.donchian = ema_fast, ema_slow, donchian
        self.atr_len, self.atr_mult, self.rr = atr_len, atr_mult, rr
        self.start_h, self.end_h, self.max_trades = start_hour_utc, end_hour_utc, max_trades_per_day
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
            return Signal(0) if h >= self.end_h else None
        if i < self.warmup or not (self.start_h <= h < self.end_h) or self.count.get(d, 0) >= self.max_trades:
            return None
        c, atr = self.close[i], self.atr[i]
        if self.ef[i] > self.es[i] and c > self.dch[i]:
            self.count[d] = self.count.get(d, 0) + 1
            return Signal(+1, stop=c - self.atr_mult * atr, rr=self.rr)
        if self.ef[i] < self.es[i] and c < self.dcl[i]:
            self.count[d] = self.count.get(d, 0) + 1
            return Signal(-1, stop=c + self.atr_mult * atr, rr=self.rr)
        return None


STRATEGIES = {"orb": ORBStrategy, "gold": GoldBreakoutStrategy}
