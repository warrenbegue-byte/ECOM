"""Gestion du risque calquée sur les règles des prop firms (FTMO, Topstep, etc.).

C'est la partie « objectif de profit + limites de risque » du reel Phantom Trader,
et la base des « règles qui tuent les comptes » du reel sur les maths des challenges.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class PropRules:
    account_size: float = 100_000.0
    profit_target_pct: float | None = 10.0   # None = pas d'objectif (compte perso / financé)
    max_daily_loss_pct: float = 5.0          # en % du capital initial
    max_total_loss_pct: float = 10.0         # en % du capital initial
    trailing_drawdown: bool = False          # plancher qui suit le plus haut (bloqué au capital initial)

    @classmethod
    def unlimited(cls, account_size: float = 100_000.0) -> "PropRules":
        """Aucune règle bloquante — utilisé pour l'optimisation."""
        return cls(account_size, None, 100.0, 100.0)


@dataclass
class RiskManager:
    rules: PropRules = field(default_factory=PropRules)
    risk_per_trade_pct: float = 0.5   # % du capital initial risqué par trade
    daily_stop_buffer: float = 0.8    # on arrête la journée à 80 % de la perte journalière max
    status: str = "active"            # active | passed | failed
    reason: str = ""
    peak: float = 0.0

    def __post_init__(self):
        self.peak = self.rules.account_size

    # --- limites -----------------------------------------------------------
    @property
    def daily_limit(self) -> float:
        return self.rules.account_size * self.rules.max_daily_loss_pct / 100

    @property
    def floor(self) -> float:
        loss = self.rules.account_size * self.rules.max_total_loss_pct / 100
        if self.rules.trailing_drawdown:
            return min(self.peak, self.rules.account_size) - loss
        return self.rules.account_size - loss

    def update(self, equity: float, day_start_equity: float) -> str:
        """À appeler à chaque bougie avec l'équité (latente incluse)."""
        if self.status != "active":
            return self.status
        self.peak = max(self.peak, equity)
        if day_start_equity - equity >= self.daily_limit:
            self.status, self.reason = "failed", "perte journalière max atteinte"
        elif equity <= self.floor:
            self.status, self.reason = "failed", "perte totale max atteinte"
        elif (self.rules.profit_target_pct is not None and
              equity >= self.rules.account_size + self.rules.account_size * self.rules.profit_target_pct / 100):
            self.status, self.reason = "passed", "objectif de profit atteint"
        return self.status

    def can_open(self, equity: float, day_start_equity: float) -> bool:
        if self.status != "active":
            return False
        return (day_start_equity - equity) < self.daily_limit * self.daily_stop_buffer

    # --- taille de position -------------------------------------------------
    def size(self, equity: float, day_start_equity: float, entry: float, stop: float,
             point_value: float = 1.0, qty_step: float = 1.0, min_qty: float = 0.0,
             max_qty: float = math.inf) -> float:
        """Quantité telle qu'un stop touché coûte risk_per_trade_pct du capital.

        Le risque est plafonné pour qu'un stop ne puisse jamais faire franchir la
        perte journalière max ni le plancher de perte totale.
        point_value : gain en devise du compte pour 1.0 de mouvement de prix et 1 unité
        (actions = 1, XAUUSD 1 lot = 100, NQ = 20, MNQ = 2).
        """
        dist = abs(entry - stop)
        if dist <= 0:
            return 0.0
        risk_amt = self.rules.account_size * self.risk_per_trade_pct / 100
        room_day = self.daily_limit * self.daily_stop_buffer - (day_start_equity - equity)
        room_total = (equity - self.floor) * 0.9
        risk_amt = min(risk_amt, room_day, room_total)
        if risk_amt <= 0:
            return 0.0
        qty = math.floor(risk_amt / (dist * point_value) / qty_step) * qty_step
        qty = min(round(qty, 8), max_qty)
        return qty if qty >= max(min_qty, qty_step) else 0.0
