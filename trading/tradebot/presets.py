"""Configurations prêtes à l'emploi : marché, frais réalistes et grille d'optimisation par bot.

Frais (conservateurs, CFD) : Nasdaq 100 = 1,5 point de spread ; or = 0,25 $ (spread + commission).
point_value : Nasdaq CFD 1 $/point/lot ; or 100 $/1 $ de mouvement/lot.
"""
from .backtest import Costs

NASDAQ = {"market": "nsxusd", "costs": Costs(spread=1.5, point_value=1.0, qty_step=0.1)}
GOLD = {"market": "xauusd", "costs": Costs(spread=0.25, point_value=100.0, qty_step=0.01)}

ORB_GRID = {
    "entry": ["breakout", "candle"],
    "range_minutes": [5, 15, 30],
    "stop_mode": ["range", "atr"],
    "stop_atr": [0.05, 0.1, 0.2],
    "rr": [0, 1.5, 3.0],
    "trend": ["none", "sma20"],
    "direction": ["both", "long"],
}

PRESETS = {
    "orb_nasdaq": {**NASDAQ, "strategy": "orb", "grid": ORB_GRID, "fixed": {}},
    "orb_gold": {**GOLD, "strategy": "orb", "grid": {**ORB_GRID, "session_open": ["08:20", "09:30"]},
                 "fixed": {}},
    "gold_breakout": {**GOLD, "strategy": "gold", "fixed": {}, "grid": {
        "donchian": [10, 20, 40],
        "atr_mult": [1.0, 2.0, 3.0],
        "rr": [0, 1.5, 3.0],
        "trail_atr": [0, 3.0],
        "breakeven_r": [0, 1.0],
        "start_hour_utc": [0, 7, 12],
        "end_hour_utc": [20, 24],
        "direction": ["both", "long"],
    }},
}
PRESETS["gold_breakout_m15"] = {**PRESETS["gold_breakout"], "resample": "15min"}
