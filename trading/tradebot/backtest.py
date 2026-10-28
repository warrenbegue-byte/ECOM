"""Backtester bougie par bougie, volontairement prudent.

Conventions (pour ne pas se mentir) :
- un signal est émis à la CLÔTURE d'une bougie, l'entrée se fait à l'OUVERTURE suivante ;
- le spread et la commission sont payés à chaque trade ;
- si le stop et l'objectif sont touchés dans la même bougie, on considère le STOP ;
- un gap au-delà du stop est exécuté au prix d'ouverture (pire prix) ;
- Signal(side=0) = sortie immédiate à la clôture de la bougie courante.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .risk import RiskManager


@dataclass
class Signal:
    side: int                    # +1 achat, -1 vente, 0 = clôturer la position
    stop: float | None = None
    rr: float | None = None      # objectif = rr x distance du stop (calculé sur le prix d'entrée réel)
    target: float | None = None  # ou objectif en prix absolu


@dataclass
class Costs:
    spread: float = 0.0          # en unités de prix, payé à l'entrée
    commission: float = 0.0      # en devise, par unité et par côté
    point_value: float = 1.0
    qty_step: float = 1.0
    min_qty: float = 0.0


@dataclass
class Trade:
    side: int
    entry_time: pd.Timestamp
    entry: float
    stop: float
    target: float | None
    qty: float
    exit_time: pd.Timestamp | None = None
    exit: float | None = None
    reason: str = ""
    pnl: float = 0.0
    r: float = 0.0


@dataclass
class Result:
    trades: list[Trade]
    equity: pd.Series
    start: float
    prop_status: str = "active"
    prop_reason: str = ""
    stats: dict = field(default_factory=dict)

    def summary(self) -> str:
        s = self.stats
        lines = [
            f"Trades            : {s['trades']}",
            f"Taux de réussite  : {s['win_rate']:.1%}",
            f"Profit factor     : {s['profit_factor']:.2f}",
            f"Espérance / trade : {s['expectancy_r']:+.3f} R",
            f"Rendement total   : {s['return_pct']:+.2f} %",
            f"Drawdown max      : {s['max_dd_pct']:.2f} %",
            f"Statut prop firm  : {self.prop_status}" + (f" ({self.prop_reason})" if self.prop_reason else ""),
        ]
        return "\n".join(lines)


def compute_stats(trades: list[Trade], equity: pd.Series, start: float) -> dict:
    pnl = np.array([t.pnl for t in trades]) if trades else np.zeros(0)
    rs = np.array([t.r for t in trades]) if trades else np.zeros(0)
    gains, losses = pnl[pnl > 0].sum(), -pnl[pnl < 0].sum()
    dd = (equity / equity.cummax() - 1).min() if len(equity) else 0.0
    return {
        "trades": len(trades),
        "win_rate": float((pnl > 0).mean()) if len(pnl) else 0.0,
        "profit_factor": float(gains / losses) if losses > 0 else (float("inf") if gains > 0 else 0.0),
        "expectancy_r": float(rs.mean()) if len(rs) else 0.0,
        "return_pct": float((equity.iloc[-1] / start - 1) * 100) if len(equity) else 0.0,
        "max_dd_pct": float(-dd * 100),
    }


def run_backtest(df: pd.DataFrame, strategy, risk: RiskManager | None = None,
                 costs: Costs | None = None, day_tz: str = "UTC") -> Result:
    risk = risk or RiskManager()
    costs = costs or Costs()
    strategy.reset()
    strategy.prepare(df)

    o, h, l, c = (df[k].to_numpy() for k in ("open", "high", "low", "close"))
    times = df.index
    days = times.tz_convert(day_tz).date
    start = equity = risk.rules.account_size
    day_start, cur_day = equity, None
    pos: Trade | None = None
    pending: Signal | None = None
    trades: list[Trade] = []
    curve = np.empty(len(df))

    def close(i: int, price: float, reason: str):
        nonlocal pos, equity
        pos.exit_time, pos.exit, pos.reason = times[i], price, reason
        gross = pos.side * (price - pos.entry) * pos.qty * costs.point_value
        pos.pnl = gross - 2 * costs.commission * pos.qty
        risk_amt = abs(pos.entry - pos.stop) * pos.qty * costs.point_value
        pos.r = pos.pnl / risk_amt if risk_amt else 0.0
        equity += pos.pnl
        trades.append(pos)
        pos = None

    for i in range(len(df)):
        if days[i] != cur_day:
            cur_day, day_start = days[i], equity

        # 1) exécution de l'ordre en attente à l'ouverture
        if pending is not None and pos is None and pending.side != 0:
            side = pending.side
            fill = o[i] + side * costs.spread
            stop = pending.stop
            valid = stop is not None and (stop < fill if side > 0 else stop > fill)
            if valid and risk.can_open(equity, day_start):
                target = pending.target
                if target is None and pending.rr:
                    target = fill + side * pending.rr * abs(fill - stop)
                qty = risk.size(equity, day_start, fill, stop, costs.point_value, costs.qty_step, costs.min_qty)
                if qty > 0:
                    pos = Trade(side, times[i], fill, stop, target, qty)
        pending = None

        # 2) stop / objectif dans la bougie
        if pos is not None:
            if pos.side > 0:
                if l[i] <= pos.stop:
                    close(i, min(o[i], pos.stop), "stop")
                elif pos.target is not None and h[i] >= pos.target:
                    close(i, max(o[i], pos.target), "objectif")
            else:
                if h[i] >= pos.stop:
                    close(i, max(o[i], pos.stop), "stop")
                elif pos.target is not None and l[i] <= pos.target:
                    close(i, min(o[i], pos.target), "objectif")

        # 3) règles prop firm sur l'équité latente
        mtm = equity + (pos.side * (c[i] - pos.entry) * pos.qty * costs.point_value if pos else 0.0)
        if risk.update(mtm, day_start) != "active" and pos is not None:
            close(i, c[i], "règle prop")
            mtm = equity
        curve[i] = mtm

        # 4) signal de la stratégie à la clôture
        sig = strategy.signal(i, pos.side if pos else 0)
        if sig is not None:
            if sig.side == 0 and pos is not None:
                close(i, c[i], "sortie stratégie")
                curve[i] = equity
            elif sig.side != 0 and pos is None and risk.status == "active":
                pending = sig

    eq = pd.Series(curve, index=times, name="equity")
    res = Result(trades, eq, start, risk.status, risk.reason)
    res.stats = compute_stats(trades, eq, start)
    return res
