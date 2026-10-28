"""« Loop Engineering » (reel @raycfu) : la boucle hypothèse -> backtest -> mesure -> ajustement.

Le piège de cette boucle, c'est le surapprentissage : à force d'itérer sur les mêmes
données, on finit toujours par trouver des paramètres « magiques » qui ne marchent
plus en réel. D'où l'analyse walk-forward : on optimise sur une fenêtre passée, on
valide sur la fenêtre SUIVANTE jamais vue, et on ne garde que ce qui tient hors échantillon.
"""
from __future__ import annotations

import itertools

import numpy as np
import pandas as pd

from .backtest import Costs, run_backtest
from .risk import PropRules, RiskManager


def _score(stats: dict, min_trades: int) -> float:
    if stats["trades"] < min_trades:
        return -np.inf
    # espérance en R pondérée par la racine du nombre de trades (favorise le robuste)
    return stats["expectancy_r"] * np.sqrt(stats["trades"])


def walk_forward(df: pd.DataFrame, strategy_cls, grid: dict, costs: Costs | None = None,
                 n_folds: int = 4, train_folds: int = 2, min_trades: int = 10,
                 risk_per_trade_pct: float = 0.5) -> dict:
    days = pd.Series(df.index.tz_convert("UTC").date, index=df.index)
    uniq = np.array(sorted(days.unique()))
    chunks = np.array_split(uniq, n_folds + train_folds)
    keys = list(grid)
    combos = [dict(zip(keys, v)) for v in itertools.product(*(grid[k] for k in keys))]

    def bt(part, params):
        risk = RiskManager(PropRules.unlimited(), risk_per_trade_pct=risk_per_trade_pct)
        return run_backtest(part, strategy_cls(**params), risk, costs)

    folds = []
    for k in range(n_folds):
        train_days = np.concatenate(chunks[k:k + train_folds])
        test_days = chunks[k + train_folds]
        train = df[days.isin(train_days).to_numpy()]
        test = df[days.isin(test_days).to_numpy()]
        scored = [(_score(bt(train, p).stats, min_trades), p) for p in combos]
        best_score, best = max(scored, key=lambda x: x[0])
        if best_score == -np.inf:
            folds.append({"fold": k + 1, "params": None, "is": None, "oos": None})
            continue
        folds.append({"fold": k + 1, "params": best, "is": bt(train, best).stats, "oos": bt(test, best).stats})

    valid = [f for f in folds if f["oos"] is not None]
    oos_r = [f["oos"]["expectancy_r"] for f in valid if f["oos"]["trades"] > 0]
    positive = sum(r > 0 for r in oos_r)
    robust = bool(oos_r) and np.mean(oos_r) > 0 and positive / len(oos_r) >= 0.6
    return {"folds": folds, "oos_mean_r": float(np.mean(oos_r)) if oos_r else 0.0,
            "positive_folds": positive, "robust": robust}


def format_report(res: dict) -> str:
    lines = ["Pli | Paramètres retenus (sur le passé)        | IS R/trade | OOS R/trade | OOS trades"]
    for f in res["folds"]:
        if f["params"] is None:
            lines.append(f"{f['fold']:>3} | pas assez de trades")
            continue
        p = ", ".join(f"{k}={v}" for k, v in f["params"].items())
        lines.append(f"{f['fold']:>3} | {p:<42} | {f['is']['expectancy_r']:+.3f}     | "
                     f"{f['oos']['expectancy_r']:+.3f}      | {f['oos']['trades']}")
    verdict = "ROBUSTE (à confirmer en démo)" if res["robust"] else "REJETÉ — probable surapprentissage / pas d'avantage"
    lines += [f"Espérance hors échantillon moyenne : {res['oos_mean_r']:+.3f} R", f"Verdict : {verdict}"]
    return "\n".join(lines)
