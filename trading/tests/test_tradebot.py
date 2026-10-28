import os
import sys
import tempfile
import unittest

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tradebot.backtest import Costs, Signal, run_backtest  # noqa: E402
from tradebot.data import load_csv, synthetic  # noqa: E402
from tradebot.optimize import walk_forward  # noqa: E402
from tradebot.propfirm import no_edge_pass_probability, simulate_challenge  # noqa: E402
from tradebot.risk import PropRules, RiskManager  # noqa: E402
from tradebot.strategies import GoldBreakoutStrategy, ORBStrategy  # noqa: E402


def ny_bars(rows, day="2026-03-10"):
    """rows = [(HH:MM, open, high, low, close)] en heure de New York, bougies 5 min."""
    idx = pd.DatetimeIndex([pd.Timestamp(f"{day} {t}", tz="America/New_York") for t, *_ in rows]).tz_convert("UTC")
    return pd.DataFrame([r[1:] for r in rows], columns=["open", "high", "low", "close"], index=idx).assign(volume=1.0)


class Scripted:
    """Stratégie de test : renvoie des signaux prédéfinis par indice de bougie."""
    name = "scripted"

    def __init__(self, signals):
        self.signals = signals

    def reset(self):
        pass

    def prepare(self, df):
        pass

    def signal(self, i, pos):
        return self.signals.get(i)


class TestPropFirm(unittest.TestCase):
    def test_formula(self):
        self.assertAlmostEqual(no_edge_pass_probability(10, 10), 0.5)
        self.assertAlmostEqual(no_edge_pass_probability(8, 5), 5 / 13)

    def test_monte_carlo_matches_formula_without_edge(self):
        sim = simulate_challenge(0.5, 1.0, 1.0, 10, 10, daily_loss_pct=None, n_sims=20_000)
        self.assertAlmostEqual(sim["pass"], 0.5, delta=0.02)

    def test_edge_increases_pass_rate(self):
        base = simulate_challenge(0.5, 1.0, 1.0, n_sims=5_000)["pass"]
        edge = simulate_challenge(0.55, 1.0, 1.0, n_sims=5_000)["pass"]
        self.assertGreater(edge, base)


class TestRisk(unittest.TestCase):
    def test_position_size(self):
        rm = RiskManager(PropRules(100_000), risk_per_trade_pct=1.0)
        self.assertEqual(rm.size(100_000, 100_000, 100.0, 99.0), 1000)
        # XAUUSD : 1 lot = 100 oz, stop à 5 $ -> 1000 / (5 * 100) = 2 lots
        self.assertAlmostEqual(rm.size(100_000, 100_000, 2400, 2395, point_value=100, qty_step=0.01), 2.0)

    def test_risk_capped_by_daily_room(self):
        rm = RiskManager(PropRules(100_000, max_daily_loss_pct=5), risk_per_trade_pct=1.0)
        # déjà -3 500 aujourd'hui : il reste 4 000*... -> 0.8*5000 - 3500 = 500 de marge
        self.assertEqual(rm.size(96_500, 100_000, 100.0, 99.0), 500)

    def test_rules(self):
        rm = RiskManager(PropRules(100_000, 10, 5, 10))
        self.assertEqual(rm.update(104_000, 100_000), "active")
        self.assertEqual(rm.update(98_900, 104_000), "failed")
        rm = RiskManager(PropRules(100_000, 10, 5, 10))
        self.assertEqual(rm.update(110_000, 106_000), "passed")


class TestBacktest(unittest.TestCase):
    def test_stop_wins_when_both_hit(self):
        df = ny_bars([("10:00", 100, 100, 100, 100), ("10:05", 100, 105, 95, 100), ("10:10", 100, 100, 100, 100)])
        res = run_backtest(df, Scripted({0: Signal(+1, stop=98, rr=1)}), RiskManager(PropRules.unlimited()))
        self.assertEqual(len(res.trades), 1)
        self.assertEqual(res.trades[0].reason, "stop")
        self.assertAlmostEqual(res.trades[0].r, -1.0)

    def test_gap_through_stop_fills_at_open(self):
        df = ny_bars([("10:00", 100, 100, 100, 100), ("10:05", 100, 100, 100, 100), ("10:10", 90, 91, 89, 90)])
        res = run_backtest(df, Scripted({0: Signal(+1, stop=98, rr=1)}), RiskManager(PropRules.unlimited()))
        self.assertAlmostEqual(res.trades[0].exit, 90)
        self.assertLess(res.trades[0].r, -1)

    def test_costs(self):
        df = ny_bars([("10:00", 100, 100, 100, 100), ("10:05", 100, 100, 100, 100), ("10:10", 100, 103, 100, 103)])
        res = run_backtest(df, Scripted({0: Signal(+1, stop=98, target=102)}), RiskManager(PropRules.unlimited()),
                           Costs(spread=0.5))
        t = res.trades[0]
        self.assertAlmostEqual(t.entry, 100.5)
        self.assertEqual(t.reason, "objectif")


class TestORB(unittest.TestCase):
    def test_long_breakout_hits_target(self):
        df = ny_bars([
            ("09:30", 100, 102, 99, 101), ("09:35", 101, 103, 100, 102), ("09:40", 102, 102, 98, 101),  # range 98-103
            ("09:45", 101, 104, 101, 104),   # clôture > 103 -> signal achat, stop 98
            ("09:50", 104, 104, 103.5, 104),  # entrée à 104, risque 6, objectif 2R = 116
            ("09:55", 104, 117, 104, 116),    # objectif touché
            ("10:00", 116, 116, 116, 116),
        ])
        res = run_backtest(df, ORBStrategy(range_minutes=15, rr=2.0), RiskManager(PropRules.unlimited()))
        self.assertEqual(len(res.trades), 1)
        t = res.trades[0]
        self.assertEqual((t.side, t.entry, t.stop, t.target, t.reason), (1, 104, 98, 116, "objectif"))
        self.assertAlmostEqual(t.r, 2.0)

    def test_no_lookahead_and_flat_at_close(self):
        df = ny_bars([
            ("09:30", 100, 101, 99, 100), ("09:35", 100, 101, 99, 100), ("09:40", 100, 101, 99, 100),
            ("09:45", 100, 100.5, 98, 98.5),  # cassure baissière -> vente, stop 101
            ("09:50", 98.5, 99, 98, 98.5), ("15:50", 98.5, 99, 98, 98.2), ("15:55", 98.2, 98.2, 98.2, 98.2),
        ])
        res = run_backtest(df, ORBStrategy(), RiskManager(PropRules.unlimited()))
        self.assertEqual(len(res.trades), 1)
        self.assertEqual(res.trades[0].side, -1)
        self.assertEqual(res.trades[0].reason, "sortie stratégie")

    def test_runs_on_synthetic(self):
        res = run_backtest(synthetic(days=30, seed=1), ORBStrategy(), RiskManager(PropRules.unlimited()))
        self.assertGreater(res.stats["trades"], 10)
        self.assertLessEqual(res.stats["trades"], 30)  # max 1 trade / jour


class TestGold(unittest.TestCase):
    def test_runs_and_respects_daily_cap(self):
        df = synthetic(days=40, seed=2)
        res = run_backtest(df, GoldBreakoutStrategy(max_trades_per_day=2), RiskManager(PropRules.unlimited()),
                           Costs(spread=0.2, point_value=100, qty_step=0.01))
        self.assertGreater(res.stats["trades"], 10)
        per_day = pd.Series([t.entry_time.date() for t in res.trades]).value_counts()
        self.assertLessEqual(per_day.max(), 2)
        for t in res.trades:
            self.assertTrue(7 <= t.entry_time.hour <= 20)


class TestWalkForward(unittest.TestCase):
    def test_random_walk_is_not_robust_by_construction(self):
        res = walk_forward(synthetic(days=90, seed=3), ORBStrategy, {"rr": [1.0, 2.0], "range_minutes": [15, 30]},
                           n_folds=3, min_trades=5)
        self.assertEqual(len(res["folds"]), 3)
        self.assertIn("robust", res)


class TestData(unittest.TestCase):
    def test_mt5_export(self):
        content = ("<DATE>\t<TIME>\t<OPEN>\t<HIGH>\t<LOW>\t<CLOSE>\t<TICKVOL>\t<VOL>\t<SPREAD>\n"
                   "2026.03.10\t16:30:00\t2400.1\t2402.0\t2399.5\t2401.2\t812\t0\t15\n"
                   "2026.03.10\t16:35:00\t2401.2\t2403.0\t2400.0\t2402.5\t640\t0\t15\n")
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as f:
            f.write(content)
        try:
            df = load_csv(f.name, tz_in="Etc/GMT-2")  # serveur UTC+2
        finally:
            os.unlink(f.name)
        self.assertEqual(df.index[0], pd.Timestamp("2026-03-10 14:30", tz="UTC"))
        self.assertEqual(df["volume"].iloc[0], 812)


class FakeMT5:
    """Faux module MetaTrader5 : sert les bougies une à une puis simule Ctrl+C."""
    ACCOUNT_TRADE_MODE_DEMO, TIMEFRAME_M5 = 0, 5
    ORDER_FILLING_FOK, ORDER_FILLING_IOC, ORDER_FILLING_RETURN = 0, 1, 2
    TRADE_ACTION_DEAL, ORDER_TYPE_BUY, ORDER_TYPE_SELL, POSITION_TYPE_BUY, ORDER_TIME_GTC = 1, 0, 1, 0, 0

    def __init__(self, df, trade_mode=0):
        import numpy as np
        self.rates = np.array(
            [(int(t.timestamp()) + 2 * 3600, *row) for t, row in zip(df.index, df[["open", "high", "low", "close", "volume"]].to_numpy())],
            dtype=[("time", "i8"), ("open", "f8"), ("high", "f8"), ("low", "f8"), ("close", "f8"), ("tick_volume", "f8")])
        self.n, self.trade_mode, self.orders = 300, trade_mode, []

    def initialize(self): return True
    def shutdown(self): pass
    def last_error(self): return (0, "")
    def symbol_select(self, *a): return True
    def positions_get(self, symbol=None): return []

    def account_info(self):
        from types import SimpleNamespace
        return SimpleNamespace(login=1, balance=10_000.0, equity=10_000.0, trade_mode=self.trade_mode)

    def symbol_info(self, s):
        from types import SimpleNamespace
        return SimpleNamespace(filling_mode=1, trade_tick_value=1.0, trade_tick_size=0.01, volume_step=0.01,
                               volume_min=0.01, volume_max=50.0, digits=2)

    def symbol_info_tick(self, s):
        from types import SimpleNamespace
        c = self.rates[self.n - 1]["close"]
        return SimpleNamespace(ask=c + 0.1, bid=c)

    def copy_rates_from_pos(self, symbol, tf, start, count):
        if self.n >= len(self.rates):
            raise KeyboardInterrupt
        self.n += 1
        return self.rates[max(0, self.n - count):self.n]

    def order_send(self, req):
        from types import SimpleNamespace
        self.orders.append(req)
        return SimpleNamespace(retcode=10009, comment="done")


class TestLiveMT5(unittest.TestCase):
    def run_with(self, fake, **kw):
        from tradebot.live_mt5 import run_live
        sys.modules["MetaTrader5"] = fake
        try:
            run_live(GoldBreakoutStrategy(), poll_seconds=0, bars=300, **kw)
        finally:
            del sys.modules["MetaTrader5"]

    def test_sends_orders_with_sl_tp_on_demo(self):
        fake = FakeMT5(synthetic(days=10, seed=4))
        self.run_with(fake, live=True)
        entries = [o for o in fake.orders if "position" not in o]
        self.assertGreater(len(entries), 0)
        for o in entries:
            self.assertGreater(o["volume"], 0)
            buy = o["type"] == FakeMT5.ORDER_TYPE_BUY
            self.assertTrue(o["sl"] < o["price"] < o["tp"] if buy else o["tp"] < o["price"] < o["sl"])

    def test_simulation_sends_nothing(self):
        fake = FakeMT5(synthetic(days=10, seed=4))
        self.run_with(fake, live=False)
        self.assertEqual(fake.orders, [])

    def test_refuses_real_account(self):
        with self.assertRaises(SystemExit):
            self.run_with(FakeMT5(synthetic(days=2), trade_mode=2), live=True)


if __name__ == "__main__":
    unittest.main()
