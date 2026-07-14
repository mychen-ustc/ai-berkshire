"""rebalance.py 回归测试（stdlib unittest，零依赖，纯 compute_orders/fx_gaps）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import rebalance as rb  # noqa: E402


class TestComputeOrders(unittest.TestCase):
    def test_buy_sell(self):
        orders = rb.compute_orders(
            current_qty={"A": 10}, prices={"A": 100, "B": 50},
            ccy={"A": "USD", "B": "USD"}, fx={"USD": 1.0},
            target_pct={"A": 40, "B": 60}, total_base=2000)
        by = {o["symbol"]: o for o in orders}
        # A: 目标 2000*40%/100 = 8股, 现10 → 卖2
        self.assertEqual(by["A"]["action"], "SELL")
        self.assertEqual(by["A"]["shares"], 2)
        # B: 目标 2000*60%/50 = 24股, 现0 → 买24
        self.assertEqual(by["B"]["action"], "BUY")
        self.assertEqual(by["B"]["shares"], 24)

    def test_auto_cut_absent_target(self):
        orders = rb.compute_orders({"A": 10}, {"A": 100}, {"A": "USD"}, {"USD": 1.0}, {}, 1000)
        self.assertEqual(orders[0]["action"], "SELL")
        self.assertEqual(orders[0]["shares"], 10)          # 缺席目标→清仓
        self.assertEqual(orders[0]["target_pct"], 0.0)

    def test_no_change_no_order(self):
        # 目标恰好=现状 → 无订单
        orders = rb.compute_orders({"A": 8}, {"A": 100}, {"A": "USD"}, {"USD": 1.0}, {"A": 100}, 800)
        self.assertEqual(orders, [])


class TestFxGaps(unittest.TestCase):
    def test_cross_ccy_gap(self):
        # 买 USD 标的(消耗USD) + 卖 CNY 标的(补CNY)，USD 现金不足则为负
        orders = [{"symbol": "US1", "ccy": "USD", "delta_base": 1000},   # 买入,消耗USD 1000
                  {"symbol": "CN1", "ccy": "CNY", "delta_base": -800}]   # 卖出,补CNY 800
        gaps = rb.fx_gaps(orders, {"USD": 200, "CNY": 0}, {"USD": 1, "CNY": 0.14})
        self.assertAlmostEqual(gaps["USD"], 200 - 1000)                 # -800 缺口
        self.assertAlmostEqual(gaps["CNY"], 0 + 800)                    # +800 富余


if __name__ == "__main__":
    unittest.main()
