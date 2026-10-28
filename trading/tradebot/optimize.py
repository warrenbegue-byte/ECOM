"""« Loop Engineering » (reel @raycfu) : la boucle hypothèse -> backtest -> mesure -> ajustement.

Le piège de cette boucle, c'est le surapprentissage : à force d'itérer sur les mêmes
données, on finit toujours par trouver des paramètres « magiques » qui ne marchent
plus en réel. Les protections mises en place ici :
1. walk-forward : on optimise sur une fenêtre passée, on mesure sur la SUIVANTE jamais vue ;
2. plateau : on choisit une zone de paramètres où les voisins marchent aussi, pas un pic isolé ;
3. score = t-stat des R (récompense un avantage régulier, pas un coup de chance) ;
4. période finale (holdout) jamais utilisée pendant l'optimisation, testée UNE seule fois,
   puis re-testée avec des frais doublés.
"""
from __future__ import annotations

import itertools
import os
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .backtest import Costs, run_backtest
from .risk import PropRules, RiskManager
from .strategies import STRATEGIES


@dataclass
class TradeSet:
    """Résultats d'un backtest réduits à l'essentiel : date d'entrée et résultat en R."""
    times: np.ndarray  # datetime64[ns] UTC
    r: np.ndarray

    def window(self, start=None, end=None) -> "TradeSet":
        m = np.ones(len(self.r), dtype=bool)
        if start is not None:
            m &= self.times >= np.datetime64(pd.Timestamp(start).tz_convert("UTC").tz_localize(None))
        if end is not None:
            m &= self.times < np.datetime64(pd.Timestamp(end).tz_convert("UTC").tz_localize(None))
        return TradeSet(self.times[m], self.r[m])

    def stats(self) -> dict:
        r, n = self.r, len(self.r)
        if n == 0:
            return {"trades": 0, "win_rate": 0.0, "profit_factor": 0.0, "expectancy_r": 0.0, "tstat": 0.0,
                    "total_r": 0.0, "max_dd_r": 0.0}
        eq = np.cumsum(r)
        dd = np.max(np.maximum.accumulate(np.r_[0, eq]) - np.r_[0, eq])
        loss = -r[r < 0].sum()
        sd = r.std(ddof=1) if n > 1 else 0.0
        return {"trades": n, "win_rate": float((r > 0).mean()),
                "profit_factor": float(r[r > 0].sum() / loss) if loss > 0 else float("inf"),
                "expectancy_r": float(r.mean()), "tstat": float(r.mean() / sd * np.sqrt(n)) if sd > 0 else 0.0,
                "total_r": float(r.sum()), "max_dd_r": float(dd)}

    def daily(self, start, end, tz: str = "America/New_York") -> list[np.ndarray]:
        """R groupés par jour de bourse (jours sans trade inclus) — pour le simulateur prop firm."""
        days = pd.bdate_range(pd.Timestamp(start).tz_convert(tz).date(), pd.Timestamp(end).tz_convert(tz).date())
        t = pd.DatetimeIndex(self.times).tz_localize("UTC").tz_convert(tz).normalize().tz_localize(None)
        by_day = pd.Series(self.r).groupby(t).apply(np.asarray) if len(self.r) else pd.Series(dtype=object)
        return [by_day.get(d, np.zeros(0)) for d in days[:-1]]


# --- exécution parallèle ------------------------------------------------------
_DF: pd.DataFrame | None = None


def _init(df):
    global _DF
    _DF = df


def _run(job) -> TradeSet:
    name, params, costs = job
    res = run_backtest(_DF, STRATEGIES[name](**params), RiskManager(PropRules.unlimited()), costs)
    times = np.array([t.entry_time.tz_convert("UTC").tz_localize(None).to_datetime64() for t in res.trades],
                     dtype="datetime64[ns]")
    return TradeSet(times, np.array([t.r for t in res.trades], dtype=float))


def run_many(df: pd.DataFrame, name: str, params_list: list[dict], costs: Costs, n_jobs: int | None = None) -> list[TradeSet]:
    n_jobs = n_jobs or os.cpu_count() or 1
    jobs = [(name, p, costs) for p in params_list]
    if n_jobs == 1 or len(jobs) == 1:
        _init(df)
        return [_run(j) for j in jobs]
    with ProcessPoolExecutor(n_jobs, initializer=_init, initargs=(df,)) as ex:
        return list(ex.map(_run, jobs, chunksize=max(1, len(jobs) // (n_jobs * 8))))


# --- sélection ----------------------------------------------------------------
def score(stats: dict, min_trades: int) -> float:
    return stats["tstat"] if stats["trades"] >= min_trades else -np.inf


class Grid:
    def __init__(self, grid: dict, fixed: dict | None = None):
        self.keys = list(grid)
        self.values = [list(grid[k]) for k in self.keys]
        self.fixed = fixed or {}
        self.index = list(itertools.product(*(range(len(v)) for v in self.values)))
        self.params = [{**self.fixed, **{k: self.values[d][j] for d, (k, j) in enumerate(zip(self.keys, idx))}}
                       for idx in self.index]
        self.numeric = [all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in v) for v in self.values]
        self._pos = {idx: k for k, idx in enumerate(self.index)}

    def select(self, sets: list[TradeSet], start, end, min_trades: int) -> int:
        """Indice de la meilleure combinaison, lissée par ses voisines sur les axes numériques."""
        raw = np.array([score(s.window(start, end).stats(), min_trades) for s in sets])
        if not np.isfinite(raw).any():
            return -1
        floor = np.nanmin(raw[np.isfinite(raw)]) - 1
        filled = np.where(np.isfinite(raw), raw, floor)
        smooth = np.full(len(raw), -np.inf)
        for k, idx in enumerate(self.index):
            if not np.isfinite(raw[k]):
                continue
            vals = [filled[k]]
            for d, num in enumerate(self.numeric):
                if not num:
                    continue
                for step in (-1, 1):
                    j = list(idx)
                    j[d] += step
                    if 0 <= j[d] < len(self.values[d]):
                        vals.append(filled[self._pos[tuple(j)]])
            smooth[k] = np.mean(vals)
        return int(np.argmax(smooth))


def make_folds(start, end, train_months: int, test_months: int) -> list[tuple]:
    folds, t0 = [], pd.Timestamp(start).normalize()
    while True:
        tr_end = t0 + pd.DateOffset(months=train_months)
        te_end = tr_end + pd.DateOffset(months=test_months)
        if te_end > pd.Timestamp(end) + pd.Timedelta(days=3):
            return folds
        folds.append((t0, tr_end, te_end))
        t0 += pd.DateOffset(months=test_months)


def walk_forward(sets: list[TradeSet], grid: Grid, folds: list[tuple], min_trades: int) -> dict:
    out, oos_t, oos_r = [], [], []
    for k, (a, b, c) in enumerate(folds, 1):
        best = grid.select(sets, a, b, min_trades)
        if best < 0:
            out.append({"fold": k, "test": f"{b:%Y-%m}→{c:%Y-%m}", "params": None})
            continue
        oos = sets[best].window(b, c)
        oos_t.append(oos.times), oos_r.append(oos.r)
        out.append({"fold": k, "test": f"{b:%Y-%m}→{c:%Y-%m}", "params": grid.params[best],
                    "is": sets[best].window(a, b).stats(), "oos": oos.stats()})
    oos = TradeSet(np.concatenate(oos_t) if oos_t else np.zeros(0, "datetime64[ns]"),
                   np.concatenate(oos_r) if oos_r else np.zeros(0))
    exp = [f["oos"]["expectancy_r"] for f in out if f.get("oos") and f["oos"]["trades"]]
    return {"folds": out, "oos": oos, "oos_stats": oos.stats(), "positive_folds": int(sum(e > 0 for e in exp)),
            "n_folds": len(exp)}


def format_wf(wf: dict) -> str:
    lines = ["Pli | Test (jamais vu) | Paramètres retenus sur les 12 mois précédents | IS R/trade | OOS R/trade | OOS trades"]
    for f in wf["folds"]:
        if f["params"] is None:
            lines.append(f"{f['fold']:>3} | {f['test']} | pas assez de trades")
            continue
        lines.append(f"{f['fold']:>3} | {f['test']}  | {short_params(f['params'])} | {f['is']['expectancy_r']:+.3f} | "
                     f"{f['oos']['expectancy_r']:+.3f} | {f['oos']['trades']}")
    s = wf["oos_stats"]
    lines.append(f"Total hors échantillon : {s['trades']} trades, {s['expectancy_r']:+.3f} R/trade, "
                 f"PF {s['profit_factor']:.2f}, {wf['positive_folds']}/{wf['n_folds']} plis positifs")
    return "\n".join(lines)


def short_params(p: dict) -> str:
    return ", ".join(f"{k}={v}" for k, v in p.items())
