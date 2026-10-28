"""Le laboratoire : optimiser PUIS tester, dans le bon ordre, sans se tromper soi-même.

  1. Développement (tout avant `holdout_start`) :
     - chaque combinaison de la grille est backtestée une fois (en parallèle) ;
     - walk-forward : 12 mois d'optimisation -> 6 mois de test, glissant ;
     - paramètres finaux = plateau optimal sur toute la période de développement.
  2. Holdout (à partir de `holdout_start`) : jamais vu pendant l'optimisation, testé une fois.
  3. Stress test : holdout avec frais doublés.
  4. Prop firm : risque par trade optimal, en rejouant les trades hors échantillon.
  5. Sauvegarde dans params/<nom>.json (réutilisable par `backtest --params` et `live --params`).
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import json
import os

import numpy as np
import pandas as pd

from .backtest import Costs
from .optimize import Grid, TradeSet, make_folds, run_many, walk_forward
from .propfirm import best_risk


def verdict(wf_stats: dict, positive: int, n_folds: int, hold: dict, stress: dict) -> str:
    wf_ok = wf_stats["expectancy_r"] > 0 and n_folds and positive / n_folds >= 0.6
    hold_ok = hold["trades"] >= 20 and hold["expectancy_r"] > 0
    if wf_ok and hold_ok and stress["expectancy_r"] > 0:
        return "VALIDÉ pour la démo"
    if wf_ok or hold_ok:
        return "FRAGILE — à surveiller, pas d'argent réel"
    return "REJETÉ"


def run_lab(df: pd.DataFrame, strategy: str, grid: dict, costs: Costs, name: str, market: str,
            holdout_start: str = "2026-01-01", train_months: int = 12, test_months: int = 6,
            min_trades: int = 30, fixed: dict | None = None, prop_rules: dict | None = None,
            n_jobs: int | None = None, out_dir: str = "params", resample: str | None = None) -> dict:
    hs = pd.Timestamp(holdout_start, tz="UTC")
    dev = df[df.index < hs]
    g = Grid(grid, fixed)
    print(f"[{name}] {len(g.params)} combinaisons x {len(dev):,} bougies de développement…", flush=True)
    sets = run_many(dev, strategy, g.params, costs, n_jobs)

    folds = make_folds(dev.index[0].tz_convert(None), hs.tz_convert(None), train_months, test_months)
    folds = [tuple(pd.Timestamp(x, tz="UTC") for x in f) for f in folds]
    wf = walk_forward(sets, g, folds, min_trades)

    best = g.select(sets, dev.index[0], hs, min_trades)
    if best < 0:
        raise RuntimeError("Aucune combinaison n'a assez de trades")
    params = g.params[best]
    dev_stats = sets[best].stats()

    full = run_many(df, strategy, [params], costs, n_jobs=1)[0]
    stress_costs = dataclasses.replace(costs, spread=costs.spread * 2, commission=costs.commission * 2)
    stressed = run_many(df, strategy, [params], stress_costs, n_jobs=1)[0]
    hold = full.window(hs, None)
    hold_stress = stressed.window(hs, None)
    end = df.index[-1]

    # prop firm : on ne rejoue que des trades hors échantillon (walk-forward + holdout)
    oos = TradeSet(np.concatenate([wf["oos"].times, hold.times]), np.concatenate([wf["oos"].r, hold.r]))
    oos_start = folds[0][1] if folds else hs
    rules = {"target_pct": 10.0, "max_loss_pct": 10.0, "daily_loss_pct": 5.0, "max_days": 60, **(prop_rules or {})}
    prop_best, prop_table = best_risk(oos.daily(oos_start, end), **rules)

    hold_s, stress_s = hold.stats(), hold_stress.stats()
    result = {
        "name": name, "strategy": strategy, "market": market, "created": dt.date.today().isoformat(),
        "data": {"start": f"{df.index[0]:%Y-%m-%d}", "end": f"{end:%Y-%m-%d}", "holdout_start": holdout_start,
                 "bars": len(df)},
        "costs": dataclasses.asdict(costs), "resample": resample, "grid": grid, "fixed": fixed or {},
        "params": params,
        "development": dev_stats,
        "walk_forward": {"folds": [{k: v for k, v in f.items()} for f in wf["folds"]], "oos": wf["oos_stats"],
                         "positive_folds": wf["positive_folds"], "n_folds": wf["n_folds"]},
        "holdout": hold_s, "holdout_stress_2x_costs": stress_s,
        "prop": {"rules": rules, "best": prop_best, "table": prop_table},
        "verdict": verdict(wf["oos_stats"], wf["positive_folds"], wf["n_folds"], hold_s, stress_s),
        "yearly_r": _yearly(full),
    }
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, f"{name}.json"), "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False, default=_json)
    return result


def _yearly(ts: TradeSet) -> dict:
    if not len(ts.r):
        return {}
    s = pd.Series(ts.r, index=pd.DatetimeIndex(ts.times))
    return {str(y): {"trades": int(len(v)), "total_r": round(float(v.sum()), 2), "expectancy_r": round(float(v.mean()), 3)}
            for y, v in s.groupby(s.index.year)}


def _json(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    return str(o)


def format_lab(res: dict) -> str:
    keys = list(res["grid"])
    p = ", ".join(f"{k}={res['params'][k]}" for k in keys)

    def row(label, s):
        return (f"{label:<34} {s['trades']:>6} {s['win_rate']:>7.1%} {s['profit_factor']:>6.2f} "
                f"{s['expectancy_r']:>+8.3f} {s['total_r']:>+8.1f} {s['max_dd_r']:>7.1f}")

    wf = res["walk_forward"]
    lines = [f"=== {res['name']} — {res['strategy']} sur {res['market']} "
             f"({res['data']['start']} → {res['data']['end']}) ===",
             f"Paramètres optimisés : {p}",
             f"{'':<34} {'trades':>6} {'réussite':>7} {'PF':>6} {'R/trade':>8} {'total R':>8} {'DD (R)':>7}",
             row("Développement (optimisé, biaisé)", res["development"]),
             row(f"Walk-forward hors échantillon", wf["oos"]),
             row(f"Holdout {res['data']['holdout_start'][:4]} (jamais vu)", res["holdout"]),
             row("Holdout, frais x2", res["holdout_stress_2x_costs"]),
             f"Plis walk-forward positifs : {wf['positive_folds']}/{wf['n_folds']}",
             "Par année (params finaux) : " + "  ".join(f"{y}: {v['total_r']:+.1f}R" for y, v in res["yearly_r"].items())]
    pr = res["prop"]
    lines.append(f"Prop firm (objectif {pr['rules']['target_pct']}%, perte max {pr['rules']['max_loss_pct']}%, "
                 f"journalière {pr['rules']['daily_loss_pct']}%, {pr['rules']['max_days']} jours) :")
    for t in pr["table"]:
        mark = " ← optimal" if t["risk_pct"] == pr["best"]["risk_pct"] else ""
        lines.append(f"   risque {t['risk_pct']:.2f}%/trade : réussite {t['pass']:.1%}, échec {t['fail']:.1%}, "
                     f"hors délai {t['timeout']:.1%}{mark}")
    lines.append(f"VERDICT : {res['verdict']}")
    return "\n".join(lines)
