"""Point d'entrée unique.  python run.py --help

Exemples :
  python run.py download xauusd 2023                       (historique 1 min gratuit -> data/)
  python run.py optimize orb_nasdaq --histdata "data/nsxusd_*.zip"
  python run.py backtest --params params/orb_nasdaq.json --histdata "data/nsxusd_*.zip"
  python run.py prop --win-rate 0.45 --rr 2 --risk 0.5
  python run.py live --params params/orb_nasdaq.json --symbol US100 --risk 0.5            (simulation)
  python run.py live --params params/orb_nasdaq.json --symbol US100 --risk 0.5 --live     (compte démo)
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import logging

from tradebot.backtest import Costs, run_backtest
from tradebot.data import download_yf, load_csv, synthetic
from tradebot.propfirm import report
from tradebot.risk import PropRules, RiskManager
from tradebot.strategies import STRATEGIES


def _data(a, resample=None):
    if a.histdata:
        from tradebot.histdata import load
        df = load(a.histdata)
    elif a.csv:
        df = load_csv(a.csv, a.tz_in)
    elif a.yf:
        df = download_yf(a.yf, a.interval, a.period)
    else:
        print("(aucune source fournie : données SYNTHÉTIQUES aléatoires, uniquement pour tester le code)")
        df = synthetic(days=90)
    resample = getattr(a, "resample", None) or resample
    if resample:
        df = df.resample(resample).agg({"open": "first", "high": "max", "low": "min", "close": "last",
                                        "volume": "sum"}).dropna()
    return df


def _load_params(path):
    with open(path) as f:
        return json.load(f)


def _strategy(a):
    """Stratégie + frais : depuis --params (fichier issu de l'optimisation) ou par défaut."""
    if a.params:
        cfg = _load_params(a.params)
        return STRATEGIES[cfg["strategy"]](**cfg["params"]), Costs(**cfg["costs"]), cfg.get("resample")
    if not a.strategy:
        raise SystemExit("Indiquez une stratégie (orb, gold) ou --params params/xxx.json")
    return STRATEGIES[a.strategy](), None, None


def _costs(a, base: Costs | None):
    c = base or Costs()
    over = {k: v for k, v in {"spread": a.spread, "commission": a.commission, "point_value": a.point_value,
                              "qty_step": a.qty_step}.items() if v is not None}
    return dataclasses.replace(c, **over)


def _rules(a):
    return PropRules(a.account or 100_000, a.target if a.target > 0 else None, a.daily_loss, a.max_loss, a.trailing)


def main():
    p = argparse.ArgumentParser(description="Bots de trading — backtest, optimisation, prop firm, live MT5")
    sub = p.add_subparsers(dest="cmd", required=True)

    def data_args(sp):
        sp.add_argument("--histdata", help='zips HistData, ex. "data/xauusd_*.zip"')
        sp.add_argument("--csv"), sp.add_argument("--tz-in", default="UTC")
        sp.add_argument("--yf", help="symbole Yahoo (GC=F, NQ=F, QQQ...)")
        sp.add_argument("--interval", default="5m"), sp.add_argument("--period", default="60d")
        sp.add_argument("--resample", help="ex. 15min, 1h")

    def cost_args(sp):
        sp.add_argument("--spread", type=float), sp.add_argument("--commission", type=float)
        sp.add_argument("--point-value", type=float), sp.add_argument("--qty-step", type=float)

    def rule_args(sp):
        sp.add_argument("--account", type=float, help="capital initial (défaut : 100000 en backtest, solde MT5 en live)")
        sp.add_argument("--target", type=float, default=10.0, help="objectif %% (0 = aucun)")
        sp.add_argument("--daily-loss", type=float, default=5.0), sp.add_argument("--max-loss", type=float, default=10.0)
        sp.add_argument("--trailing", action="store_true")

    dl = sub.add_parser("download", help="télécharger l'historique 1 minute HistData.com")
    dl.add_argument("pair", help="xauusd, nsxusd, spxusd, eurusd…")
    dl.add_argument("start_year", type=int), dl.add_argument("--end-year", type=int)
    dl.add_argument("--dest", default="data")

    from tradebot.presets import PRESETS
    op = sub.add_parser("optimize", help="optimiser puis tester un bot (walk-forward + holdout + prop firm)")
    op.add_argument("preset", choices=PRESETS)
    data_args(op), cost_args(op)
    op.add_argument("--holdout", default="2026-01-01", help="début de la période finale jamais vue")
    op.add_argument("--min-trades", type=int, default=30)
    op.add_argument("--jobs", type=int, help="processus en parallèle (défaut : tous les cœurs)")
    op.add_argument("--out", default="params")

    bt = sub.add_parser("backtest", help="tester une stratégie sur l'historique")
    bt.add_argument("strategy", nargs="?", choices=STRATEGIES)
    bt.add_argument("--params", help="fichier params/xxx.json produit par optimize")
    bt.add_argument("--risk", type=float, default=0.5, help="%% du capital risqué par trade")
    bt.add_argument("--from", dest="start"), bt.add_argument("--to", dest="end")
    data_args(bt), cost_args(bt), rule_args(bt)
    bt.add_argument("--trades-csv", help="exporter la liste des trades")

    pr = sub.add_parser("prop", help="probabilité de réussir un challenge prop firm")
    pr.add_argument("--win-rate", type=float, required=True), pr.add_argument("--rr", type=float, required=True)
    pr.add_argument("--risk", type=float, default=0.5)
    pr.add_argument("--target", type=float, default=10.0), pr.add_argument("--max-loss", type=float, default=10.0)
    pr.add_argument("--daily-loss", type=float, default=5.0)
    pr.add_argument("--trades-per-day", type=int, default=2), pr.add_argument("--max-days", type=int)
    pr.add_argument("--fee", type=float, help="prix du challenge")

    lv = sub.add_parser("live", help="bot MetaTrader 5 en local (simulation par défaut)")
    lv.add_argument("strategy", nargs="?", choices=STRATEGIES)
    lv.add_argument("--params", help="fichier params/xxx.json produit par optimize")
    lv.add_argument("--symbol", default="XAUUSD"), lv.add_argument("--timeframe")
    lv.add_argument("--risk", type=float, default=0.25)
    lv.add_argument("--server-utc-offset", type=float, default=2.0, help="décalage horaire du serveur broker (souvent 2 ou 3)")
    lv.add_argument("--live", action="store_true", help="envoyer réellement les ordres")
    lv.add_argument("--allow-real", action="store_true", help="autoriser un compte réel (déconseillé)")
    rule_args(lv)

    a = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    if a.cmd == "download":
        from tradebot.histdata import download
        files = download(a.pair, a.start_year, a.end_year, a.dest)
        print(f"{len(files)} fichiers dans {a.dest}/")
    elif a.cmd == "prop":
        print(report(a.win_rate, a.rr, a.risk, a.target, a.max_loss, a.daily_loss or None,
                     a.trades_per_day, a.max_days, a.fee))
    elif a.cmd == "optimize":
        from tradebot.lab import format_lab, run_lab
        pre = PRESETS[a.preset]
        df = _data(a, pre.get("resample"))
        res = run_lab(df, pre["strategy"], pre["grid"], _costs(a, pre["costs"]), a.preset, pre["market"],
                      holdout_start=a.holdout, min_trades=a.min_trades, fixed=pre["fixed"], n_jobs=a.jobs,
                      out_dir=a.out, resample=pre.get("resample"))
        print(format_lab(res))
        print(f"\nParamètres sauvegardés : {a.out}/{a.preset}.json")
    elif a.cmd == "backtest":
        strat, base_costs, resample = _strategy(a)
        df = _data(a, resample)
        if a.start:
            df = df[df.index >= a.start]
        if a.end:
            df = df[df.index < a.end]
        res = run_backtest(df, strat, RiskManager(_rules(a), a.risk), _costs(a, base_costs))
        print(res.summary())
        if a.trades_csv:
            import pandas as pd
            pd.DataFrame([t.__dict__ for t in res.trades]).to_csv(a.trades_csv, index=False)
    elif a.cmd == "live":
        from tradebot.live_mt5 import run_live
        strat, _, resample = _strategy(a)
        timeframe = a.timeframe or {"15min": "M15", "1h": "H1"}.get(resample, "M5")
        rules = _rules(a)
        rules.account_size = a.account  # None -> solde du compte MT5
        run_live(strat, a.symbol, timeframe, a.risk, rules, a.server_utc_offset, a.live, a.allow_real)


if __name__ == "__main__":
    main()
