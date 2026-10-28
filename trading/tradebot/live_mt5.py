"""Bot live sur MetaTrader 5, exécuté en local sur votre PC (Windows).

Sécurités :
- par défaut : SIMULATION (aucun ordre envoyé, tout est journalisé) ;
- --live : envoie les ordres, mais refuse un compte RÉEL sauf --allow-real ;
- garde-fous prop firm (perte journalière / totale) vérifiés à chaque bougie ;
- n'agit que sur ses propres positions (numéro magique).
Prérequis : terminal MetaTrader 5 installé, ouvert et connecté, « Algo Trading » activé,
puis `pip install MetaTrader5` (paquet Windows uniquement).
"""
from __future__ import annotations

import logging
import time

import pandas as pd

from .risk import PropRules, RiskManager

log = logging.getLogger("tradebot.live")


def _filling(mt5, info) -> int:
    if info.filling_mode & 1:
        return mt5.ORDER_FILLING_FOK
    if info.filling_mode & 2:
        return mt5.ORDER_FILLING_IOC
    return mt5.ORDER_FILLING_RETURN


def run_live(strategy, symbol: str = "XAUUSD", timeframe: str = "M5", risk_pct: float = 0.25,
             rules: PropRules | None = None, server_utc_offset: float = 2.0, live: bool = False,
             allow_real: bool = False, magic: int = 20261028, poll_seconds: float = 2.0, bars: int = 600):
    try:
        import MetaTrader5 as mt5
    except ImportError as e:
        raise SystemExit("Installez le paquet : pip install MetaTrader5 (Windows + terminal MT5 requis)") from e

    if not mt5.initialize():
        raise SystemExit(f"Impossible de se connecter au terminal MT5 : {mt5.last_error()}")
    acc = mt5.account_info()
    is_demo = acc.trade_mode == mt5.ACCOUNT_TRADE_MODE_DEMO
    if live and not is_demo and not allow_real:
        mt5.shutdown()
        raise SystemExit("Compte RÉEL détecté : refusé. Testez en démo, ou ajoutez --allow-real en connaissance de cause.")
    if not mt5.symbol_select(symbol, True):
        raise SystemExit(f"Symbole introuvable chez ce broker : {symbol}")

    rules = rules or PropRules(account_size=None, profit_target_pct=None)
    if rules.account_size is None:
        rules.account_size = acc.balance
    risk = RiskManager(rules, risk_per_trade_pct=risk_pct)
    tf = getattr(mt5, f"TIMEFRAME_{timeframe}")
    mode = "LIVE" if live else "SIMULATION"
    log.info("%s | compte %s (%s) | %s %s | risque %.2f %%/trade", mode, acc.login,
             "démo" if is_demo else "RÉEL", symbol, timeframe, risk_pct)

    strategy.reset()
    last_bar, cur_day, day_start = None, None, acc.equity
    init_risk: dict[int, float] = {}  # risque initial (1 R) par ticket, pour le breakeven

    def my_positions():
        return [p for p in (mt5.positions_get(symbol=symbol) or []) if p.magic == magic]

    def send(req):
        if not live:
            log.info("[SIMULATION] ordre non envoyé : %s", req)
            return
        r = mt5.order_send(req)
        log.info("Ordre envoyé -> retcode %s %s", getattr(r, "retcode", None), getattr(r, "comment", mt5.last_error()))

    def close_all(reason):
        info = mt5.symbol_info(symbol)
        for p in my_positions():
            tick = mt5.symbol_info_tick(symbol)
            buy = p.type == mt5.POSITION_TYPE_BUY
            send({"action": mt5.TRADE_ACTION_DEAL, "symbol": symbol, "volume": p.volume, "position": p.ticket,
                  "type": mt5.ORDER_TYPE_SELL if buy else mt5.ORDER_TYPE_BUY,
                  "price": tick.bid if buy else tick.ask, "deviation": 20, "magic": magic,
                  "comment": reason[:31], "type_filling": _filling(mt5, info)})

    try:
        while True:
            rates = mt5.copy_rates_from_pos(symbol, tf, 0, bars)
            if rates is None or len(rates) < 3:
                time.sleep(poll_seconds)
                continue
            df = pd.DataFrame(rates)
            idx = pd.to_datetime(df["time"], unit="s") - pd.Timedelta(hours=server_utc_offset)
            df = df.rename(columns={"tick_volume": "volume"}).set_index(pd.DatetimeIndex(idx).tz_localize("UTC"))
            df = df[["open", "high", "low", "close", "volume"]].iloc[:-1]  # la dernière bougie est en cours
            if df.index[-1] == last_bar:
                time.sleep(poll_seconds)
                continue
            last_bar = df.index[-1]

            equity = mt5.account_info().equity
            if df.index[-1].date() != cur_day:
                cur_day, day_start = df.index[-1].date(), equity
            if risk.update(equity, day_start) != "active":
                log.warning("Règle atteinte : %s -> clôture et arrêt", risk.reason)
                close_all("regle prop")
                break

            positions = my_positions()
            pos = 0 if not positions else (1 if positions[0].type == mt5.POSITION_TYPE_BUY else -1)
            strategy.prepare(df)
            if positions and hasattr(strategy, "manage"):
                for p in positions:  # stop suiveur / breakeven : on ne fait que resserrer le SL
                    risk0 = init_risk.setdefault(p.ticket, abs(p.price_open - p.sl) if p.sl else 0.0)
                    new = strategy.manage(len(df) - 1, pos, p.price_open, p.sl, risk0)
                    if p.sl and new is not None and (new - p.sl) * pos > 0:
                        send({"action": mt5.TRADE_ACTION_SLTP, "symbol": symbol, "position": p.ticket,
                              "sl": round(new, mt5.symbol_info(symbol).digits), "tp": p.tp, "magic": magic})
            sig = strategy.signal(len(df) - 1, pos)
            if sig is None:
                continue
            if sig.side == 0:
                if pos:
                    close_all("sortie strategie")
                continue
            if pos or not risk.can_open(equity, day_start):
                continue

            info, tick = mt5.symbol_info(symbol), mt5.symbol_info_tick(symbol)
            price = tick.ask if sig.side > 0 else tick.bid
            if (sig.side > 0 and sig.stop >= price) or (sig.side < 0 and sig.stop <= price):
                log.info("Signal ignoré : le prix a déjà dépassé le stop")
                continue
            target = sig.target or (price + sig.side * sig.rr * abs(price - sig.stop) if sig.rr else 0.0)
            point_value = info.trade_tick_value / info.trade_tick_size
            vol = risk.size(equity, day_start, price, sig.stop, point_value, info.volume_step,
                            info.volume_min, info.volume_max)
            if vol <= 0:
                log.info("Signal ignoré : volume calculé nul (stop trop large ou marge de risque épuisée)")
                continue
            digits = info.digits
            send({"action": mt5.TRADE_ACTION_DEAL, "symbol": symbol, "volume": vol,
                  "type": mt5.ORDER_TYPE_BUY if sig.side > 0 else mt5.ORDER_TYPE_SELL, "price": price,
                  "sl": round(sig.stop, digits), "tp": round(target, digits), "deviation": 20, "magic": magic,
                  "comment": f"tradebot {strategy.name}", "type_time": mt5.ORDER_TIME_GTC,
                  "type_filling": _filling(mt5, info)})
    except KeyboardInterrupt:
        log.info("Arrêt demandé (Ctrl+C). Les positions ouvertes restent protégées par leur SL/TP.")
    finally:
        mt5.shutdown()
