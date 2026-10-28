"""Historique gratuit en bougies 1 minute depuis HistData.com (plusieurs années).

Symboles utiles : xauusd (or), nsxusd (Nasdaq 100), spxusd (S&P 500), eurusd...
Les années terminées se téléchargent en un fichier, l'année en cours mois par mois.
Les horodatages suivent l'heure de New York (pause quotidienne à 17h toute l'année).
Données réservées à un usage personnel : ne pas les redistribuer (elles ne sont pas versionnées).
"""
from __future__ import annotations

import datetime as dt
import glob
import io
import os
import re
import time
import urllib.parse
import urllib.request
import zipfile

import pandas as pd

BASE = "https://www.histdata.com/download-free-forex-historical-data/?/ascii/1-minute-bar-quotes"
UA = {"User-Agent": "Mozilla/5.0"}


def _fetch(pair: str, year: int, month: int | None) -> bytes:
    path = f"{year}/{month}" if month else f"{year}"
    ref = f"{BASE}/{pair.lower()}/{path}"
    page = urllib.request.urlopen(urllib.request.Request(ref, headers=UA), timeout=60).read().decode("utf-8", "ignore")
    tk = re.search(r'id="tk" value="([^"]+)"', page)
    if not tk:
        raise RuntimeError(f"Jeton HistData introuvable pour {pair} {path}")
    form = {"tk": tk.group(1), "date": str(year), "datemonth": f"{year}{month:02d}" if month else str(year),
            "platform": "ASCII", "timeframe": "M1", "fxpair": pair.upper()}
    req = urllib.request.Request("https://www.histdata.com/get.php", data=urllib.parse.urlencode(form).encode(),
                                 headers={**UA, "Referer": ref})
    data = urllib.request.urlopen(req, timeout=120).read()
    if not data.startswith(b"PK"):
        raise RuntimeError(f"Pas de fichier pour {pair} {path} (période indisponible ?)")
    return data


def download(pair: str, start_year: int, end_year: int | None = None, dest: str = "data", pause: float = 2.0) -> list[str]:
    """Télécharge les zips dans dest/ (ignore ceux déjà présents). Renvoie la liste des fichiers."""
    os.makedirs(dest, exist_ok=True)
    today = dt.date.today()
    end_year = end_year or today.year
    jobs = []
    for y in range(start_year, end_year + 1):
        if y < today.year:
            jobs.append((y, None))
        else:
            jobs += [(y, m) for m in range(1, today.month)]
    files = []
    for y, m in jobs:
        out = os.path.join(dest, f"{pair.lower()}_{y}{'' if m is None else f'{m:02d}'}.zip")
        if not os.path.exists(out):
            try:
                with open(out, "wb") as f:
                    f.write(_fetch(pair, y, m))
                print(f"téléchargé : {out}")
                time.sleep(pause)
            except Exception as e:  # mois pas encore publié, coupure réseau...
                if os.path.exists(out):
                    os.remove(out)
                print(f"ignoré {pair} {y}{'' if m is None else f'-{m:02d}'} : {e}")
                continue
        files.append(out)
    return files


def load(pattern: str, freq: str | None = "5min") -> pd.DataFrame:
    """Charge les zips HistData (motif glob, ex. "data/xauusd_*.zip") -> OHLCV UTC, rééchantillonné à freq."""
    parts = []
    for path in sorted(glob.glob(pattern)):
        with zipfile.ZipFile(path) as z:
            name = next(n for n in z.namelist() if n.endswith(".csv"))
            raw = z.read(name)
        parts.append(pd.read_csv(io.BytesIO(raw), sep=";", header=None,
                                 names=["time", "open", "high", "low", "close", "volume"]))
    if not parts:
        raise FileNotFoundError(f"Aucun fichier ne correspond à {pattern}")
    df = pd.concat(parts, ignore_index=True)
    idx = pd.to_datetime(df.pop("time"), format="%Y%m%d %H%M%S")
    idx = pd.DatetimeIndex(idx).tz_localize("America/New_York", ambiguous="NaT", nonexistent="NaT")
    df.index = idx
    df = df[df.index.notna()]
    df.index = df.index.tz_convert("UTC")
    df = df[~df.index.duplicated()].sort_index()
    if freq:
        df = df.resample(freq, label="left", closed="left").agg(
            {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
    df.index.name = "time"
    return df.astype(float)
