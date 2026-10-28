"""Point d'entrée unique.  python run.py --help

Exemples :
  python run.py prop --win-rate 0.45 --rr 2 --risk 0.5
  python run.py backtest orb --yf NQ=F --interval 5m --point-value 20 --qty-step 1
  python run.py backtest gold --csv XAUUSD_M5.csv --tz-in Etc/GMT-2 --point-value 100 --qty-step 0.01 --spread 0.2
  python run.py optimize orb --yf QQQ --interval 5m
  python run.py live gold --symbol XAUUSD --timeframe M5            (simulation)
  python run.py live gold --symbol XAUUSD --timeframe M5 --live     (ordres réels sur compte démo)
"""
from __future__ import annotations

import argparse
import logging

from tradebot.backtest import Costs, run_backtest
from tradebot.data import download_yf, load_csv, synthetic
from tradebot.optimize import format_report, walk_forward
from tradebot.propfirm import report
from tradebot.risk import PropRules, RiskManager
from tradebot.strategies import STRATEGIES

GRIDS = {
    "orb": {"range_minutes": [5, 15, 30], "rr": [1.0, 1.5, 2.0, 3.0], "stop_mode": ["range", "mid"]},
    "gold": {"donchian": [10, 20, 40], "atr_mult": [1.0, 1.5, 2.5], "rr": [1.0, 1.5, 2.5]},
}


def _data(a):
    if a.csv:
        return load_csv(a.csv, a.tz_in)
    if a.yf:
        return download_yf(a.yf, a.interval, a.period)
    print("(aucune source fournie : données SYNTHÉTIQUES aléatoires, uniquement pour tester le code)")
    return synthetic(days=90)


def _costs(a):
    return Costs(spread=a.spread, commission=a.commission, point_value=a.point_value, qty_step=a.qty_step)


def _rules(a):
    return PropRules(a.account or 100_000, a.target if a.target > 0 else None, a.daily_loss, a.max_loss, a.trailing)


def main():
    p = argparse.ArgumentParser(description="Bots de trading — backtest, optimisation, prop firm, live MT5")
    sub = p.add_subparsers(dest="cmd", required=True)

    def data_args(sp):
        sp.add_argument("strategy", choices=STRATEGIES)
        sp.add_argument("--csv"), sp.add_argument("--tz-in", default="UTC")
        sp.add_argument("--yf", help="symbole Yahoo (GC=F, NQ=F, QQQ...)")
        sp.add_argument("--interval", default="5m"), sp.add_argument("--period", default="60d")
        sp.add_argument("--spread", type=float, default=0.0), sp.add_argument("--commission", type=float, default=0.0)
        sp.add_argument("--point-value", type=float, default=1.0), sp.add_argument("--qty-step", type=float, default=1.0)
        sp.add_argument("--risk", type=float, default=0.5, help="%% du capital risqué par trade")

    def rule_args(sp):
        sp.add_argument("--account", type=float, help="capital initial (défaut : 100000 en backtest, solde MT5 en live)")
        sp.add_argument("--target", type=float, default=10.0, help="objectif %% (0 = aucun)")
        sp.add_argument("--daily-loss", type=float, default=5.0), sp.add_argument("--max-loss", type=float, default=10.0)
        sp.add_argument("--trailing", action="store_true")

    bt = sub.add_parser("backtest", help="tester une stratégie sur l'historique")
    data_args(bt), rule_args(bt)
    bt.add_argument("--trades-csv", help="exporter la liste des trades")

    op = sub.add_parser("optimize", help="boucle walk-forward (Loop Engineering sans surapprentissage)")
    data_args(op)
    op.add_argument("--folds", type=int, default=4)
    op.add_argument("--min-trades", type=int, default=10)

    pr = sub.add_parser("prop", help="probabilité de réussir un challenge prop firm")
    pr.add_argument("--win-rate", type=float, required=True), pr.add_argument("--rr", type=float, required=True)
    pr.add_argument("--risk", type=float, default=0.5)
    pr.add_argument("--target", type=float, default=10.0), pr.add_argument("--max-loss", type=float, default=10.0)
    pr.add_argument("--daily-loss", type=float, default=5.0)
    pr.add_argument("--trades-per-day", type=int, default=2), pr.add_argument("--max-days", type=int)
    pr.add_argument("--fee", type=float, help="prix du challenge")

    lv = sub.add_parser("live", help="bot MetaTrader 5 en local (simulation par défaut)")
    lv.add_argument("strategy", choices=STRATEGIES)
    lv.add_argument("--symbol", default="XAUUSD"), lv.add_argument("--timeframe", default="M5")
    lv.add_argument("--risk", type=float, default=0.25)
    lv.add_argument("--server-utc-offset", type=float, default=2.0, help="décalage horaire du serveur broker (souvent 2 ou 3)")
    lv.add_argument("--live", action="store_true", help="envoyer réellement les ordres")
    lv.add_argument("--allow-real", action="store_true", help="autoriser un compte réel (déconseillé)")
    rule_args(lv)

    a = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    if a.cmd == "prop":
        print(report(a.win_rate, a.rr, a.risk, a.target, a.max_loss, a.daily_loss or None,
                     a.trades_per_day, a.max_days, a.fee))
    elif a.cmd == "backtest":
        res = run_backtest(_data(a), STRATEGIES[a.strategy](), RiskManager(_rules(a), a.risk), _costs(a))
        print(res.summary())
        if a.trades_csv:
            import pandas as pd
            pd.DataFrame([t.__dict__ for t in res.trades]).to_csv(a.trades_csv, index=False)
    elif a.cmd == "optimize":
        res = walk_forward(_data(a), STRATEGIES[a.strategy], GRIDS[a.strategy], _costs(a),
                           n_folds=a.folds, min_trades=a.min_trades, risk_per_trade_pct=a.risk)
        print(format_report(res))
    elif a.cmd == "live":
        from tradebot.live_mt5 import run_live
        rules = _rules(a)
        rules.account_size = a.account  # None -> solde du compte MT5
        run_live(STRATEGIES[a.strategy](), a.symbol, a.timeframe, a.risk, rules,
                 a.server_utc_offset, a.live, a.allow_real)


if __name__ == "__main__":
    main()
