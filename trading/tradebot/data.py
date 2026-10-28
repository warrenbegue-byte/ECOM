"""Chargement des données OHLCV (CSV, export MetaTrader 5, Yahoo Finance, synthétique).

Toutes les fonctions renvoient un DataFrame indexé en UTC (tz-aware) avec les
colonnes : open, high, low, close, volume. L'horodatage est l'OUVERTURE de la bougie.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

COLS = ["open", "high", "low", "close", "volume"]


def _finalize(df: pd.DataFrame, idx: pd.DatetimeIndex, tz_in: str) -> pd.DataFrame:
    idx = pd.DatetimeIndex(idx)
    idx = idx.tz_localize(tz_in) if idx.tz is None else idx
    df = df.set_index(idx.tz_convert("UTC"))
    df.index.name = "time"
    if "volume" not in df.columns:
        df["volume"] = df["tickvol"] if "tickvol" in df.columns else 0.0
    return df[COLS].astype(float).sort_index()


def load_csv(path: str, tz_in: str = "UTC") -> pd.DataFrame:
    """Lit un CSV classique ou un export MT5 (<DATE> <TIME> <OPEN> ... séparés par tab).

    tz_in : fuseau des horodatages du fichier si non précisé (ex. "Etc/GMT-2" pour un
    serveur MT5 en UTC+2 — attention, le signe est inversé dans la notation Etc/GMT).
    """
    df = pd.read_csv(path, sep=None, engine="python")
    df.columns = [c.strip().strip("<>").lower() for c in df.columns]
    if "date" in df.columns and "time" in df.columns:
        idx = pd.to_datetime(df["date"].astype(str) + " " + df["time"].astype(str))
    else:
        col = next(c for c in ("datetime", "timestamp", "time", "date") if c in df.columns)
        idx = pd.to_datetime(df[col])
    return _finalize(df, idx, tz_in)


def download_yf(symbol: str, interval: str = "5m", period: str = "60d") -> pd.DataFrame:
    """Télécharge via Yahoo Finance (pip install yfinance).

    Limites Yahoo : 1m = 7 jours max, 5m/15m = 60 jours max, 1h = 730 jours.
    Exemples de symboles : GC=F (or futures), NQ=F (Nasdaq futures), QQQ, SPY.
    """
    import yfinance as yf

    raw = yf.download(symbol, interval=interval, period=period, auto_adjust=False, progress=False)
    if raw.empty:
        raise ValueError(f"Aucune donnée Yahoo pour {symbol} ({interval}, {period})")
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    raw.columns = [c.lower() for c in raw.columns]
    return _finalize(raw, raw.index, "UTC")


def synthetic(days: int = 60, freq: str = "5min", start: str = "2026-01-05", seed: int = 0,
              price: float = 2000.0, vol: float = 0.0008) -> pd.DataFrame:
    """Marche aléatoire 24h/24 en jours ouvrés — pour les tests, pas pour juger une stratégie."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range(start, periods=int(pd.Timedelta(days=days) / pd.Timedelta(freq)), freq=freq, tz="UTC")
    idx = idx[idx.dayofweek < 5]
    rets = rng.normal(0, vol, len(idx))
    close = price * np.exp(np.cumsum(rets))
    open_ = np.r_[price, close[:-1]]
    wick = np.abs(rng.normal(0, vol / 2, len(idx))) * close
    high = np.maximum(open_, close) + wick
    low = np.minimum(open_, close) - wick
    df = pd.DataFrame({"open": open_, "high": high, "low": low, "close": close,
                       "volume": rng.integers(50, 500, len(idx)).astype(float)}, index=idx)
    df.index.name = "time"
    return df
