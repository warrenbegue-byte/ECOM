"""Les maths des challenges prop firm (reel @davidtrades_model, papier SSRN).

Un challenge = une course entre un objectif de profit T et une limite de perte L.
Sans avantage statistique (marche aléatoire), la probabilité de réussir vaut :

        P(réussite) = L / (L + T)

(ruine du joueur à espérance nulle). Exemple : objectif 10 %, perte max 10 % -> 50 %.
Objectif 8 %, perte max 5 % -> 38 %. Et la perte journalière max, les frais et le temps
limité font baisser ce chiffre. Seule une espérance positive le fait monter :
la simulation Monte Carlo ci-dessous le quantifie.
"""
from __future__ import annotations

import numpy as np


def no_edge_pass_probability(target_pct: float, max_loss_pct: float) -> float:
    return max_loss_pct / (max_loss_pct + target_pct)


def breakeven_win_rate(rr: float) -> float:
    """Taux de réussite minimal pour une espérance nulle avec un ratio gain/risque rr."""
    return 1 / (1 + rr)


def simulate_challenge(win_rate: float, rr: float, risk_pct: float, target_pct: float = 10.0,
                       max_loss_pct: float = 10.0, daily_loss_pct: float | None = 5.0,
                       trades_per_day: int = 2, max_days: int | None = None,
                       n_sims: int = 20_000, seed: int = 0) -> dict:
    """Monte Carlo d'un challenge. Toutes les valeurs sont en % du capital initial.

    max_days=None : pas de limite de temps (la plupart des prop firms en 2026).
    """
    rng = np.random.default_rng(seed)
    eq = np.zeros(n_sims)
    status = np.zeros(n_sims, dtype=int)  # 0 en cours, 1 réussi, -1 échoué
    days_used = np.zeros(n_sims)
    day, horizon = 0, max_days or 2_000
    while day < horizon and (status == 0).any():
        day += 1
        day_start = eq.copy()
        for _ in range(trades_per_day):
            live = status == 0
            if daily_loss_pct is not None:  # le trader s'arrête avant de franchir la limite du jour
                live &= (day_start - eq) + risk_pct < daily_loss_pct - 1e-9
            wins = rng.random(n_sims) < win_rate
            eq = np.where(live, eq + np.where(wins, rr * risk_pct, -risk_pct), eq)
            passed = (status == 0) & (eq >= target_pct)
            failed = (status == 0) & (eq <= -max_loss_pct)
            status[passed], status[failed] = 1, -1
            days_used[passed | failed] = day
    done = status != 0
    return {
        "pass": float((status == 1).mean()),
        "fail": float((status == -1).mean()),
        "timeout": float((status == 0).mean()),
        "avg_days": float(days_used[done].mean()) if done.any() else float("nan"),
        "expectancy_r": win_rate * rr - (1 - win_rate),
    }


def report(win_rate: float, rr: float, risk_pct: float, target_pct: float, max_loss_pct: float,
           daily_loss_pct: float | None, trades_per_day: int, max_days: int | None, fee: float | None = None) -> str:
    sim = simulate_challenge(win_rate, rr, risk_pct, target_pct, max_loss_pct, daily_loss_pct,
                             trades_per_day, max_days)
    lines = [
        f"Sans avantage (formule L/(L+T))  : {no_edge_pass_probability(target_pct, max_loss_pct):.1%}",
        f"Taux de réussite d'équilibre     : {breakeven_win_rate(rr):.1%} (pour RR {rr})",
        f"Espérance de votre stratégie     : {sim['expectancy_r']:+.3f} R / trade",
        f"Probabilité de RÉUSSIR           : {sim['pass']:.1%}",
        f"Probabilité d'ÉCHOUER            : {sim['fail']:.1%}",
        f"Hors délai                       : {sim['timeout']:.1%}",
        f"Durée moyenne                    : {sim['avg_days']:.1f} jours",
    ]
    if fee and sim["pass"] > 0:
        lines.append(f"Coût moyen pour obtenir 1 compte : {fee / sim['pass']:.0f} (frais {fee:.0f} / proba)")
    return "\n".join(lines)


def simulate_from_daily(daily_r: list[np.ndarray], risk_pct: float, target_pct: float = 10.0,
                        max_loss_pct: float = 10.0, daily_loss_pct: float | None = 5.0,
                        max_days: int | None = None, n_sims: int = 10_000, seed: int = 0) -> dict:
    """Challenge simulé en rejouant de VRAIES journées de trading tirées au hasard (bootstrap par jour).

    daily_r : liste de tableaux de R, un par jour de bourse (vide = jour sans trade). Garder les
    journées entières conserve les séries de pertes intrajournalières et le nombre de trades par jour.
    """
    rng = np.random.default_rng(seed)
    k = max((len(d) for d in daily_r), default=0)
    if k == 0:
        return {"risk_pct": risk_pct, "pass": 0.0, "fail": 0.0, "timeout": 1.0, "median_days": float("nan")}
    mat = np.full((len(daily_r), k), np.nan)
    for j, d in enumerate(daily_r):
        mat[j, :len(d)] = d
    eq = np.zeros(n_sims)
    status = np.zeros(n_sims, dtype=int)
    days_used = np.zeros(n_sims)
    horizon = max_days or 750
    for day in range(1, horizon + 1):
        rows = mat[rng.integers(len(daily_r), size=n_sims)]
        day_start = eq.copy()
        for t in range(k):
            r = rows[:, t]
            live = (status == 0) & ~np.isnan(r)
            if daily_loss_pct is not None:  # le bot s'arrête pour la journée avant de risquer la limite
                live &= (day_start - eq) + risk_pct < daily_loss_pct - 1e-9
            eq = np.where(live, eq + np.nan_to_num(r) * risk_pct, eq)
            breach = eq <= -max_loss_pct
            if daily_loss_pct is not None:
                breach |= day_start - eq >= daily_loss_pct
            fail_now = (status == 0) & breach
            pass_now = (status == 0) & ~fail_now & (eq >= target_pct)
            status[fail_now], status[pass_now] = -1, 1
            days_used[fail_now | pass_now] = day
        if not (status == 0).any():
            break
    passed = status == 1
    return {"risk_pct": risk_pct, "pass": float(passed.mean()), "fail": float((status == -1).mean()),
            "timeout": float((status == 0).mean()),
            "median_days": float(np.median(days_used[passed])) if passed.any() else float("nan")}


def best_risk(daily_r: list[np.ndarray], risks=(0.25, 0.5, 0.75, 1.0, 1.5, 2.0), **rules) -> tuple[dict, list[dict]]:
    """Balaye le risque par trade et renvoie (meilleur, tableau complet).

    À probabilité quasi égale (< 2 points d'écart), on préfère le risque le plus faible.
    """
    table = [simulate_from_daily(daily_r, r, **rules) for r in risks]
    top = max(t["pass"] for t in table)
    best = next(t for t in table if t["pass"] >= top - 0.02)
    return best, table
