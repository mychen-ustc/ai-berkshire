"""signal_lab.py 回归测试（防过拟合工具箱纯函数，零依赖）。"""
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import signal_lab as sl  # noqa: E402


class TestEffectiveObs(unittest.TestCase):
    def test_non_overlapping(self):
        # 触发相距 >= horizon → 全独立
        self.assertEqual(sl.effective_independent_obs([0, 20, 40, 60], 20), 4)

    def test_clustered_overlap(self):
        # 密集触发落在同一前瞻窗 → 被压缩
        self.assertEqual(sl.effective_independent_obs([0, 5, 10, 15, 20], 20), 2)  # 0..20 claims [0,20); 20 独立

    def test_dedup_and_sort(self):
        self.assertEqual(sl.effective_independent_obs([40, 0, 0, 20], 20), 3)

    def test_bad_horizon(self):
        with self.assertRaises(ValueError):
            sl.effective_independent_obs([1, 2], 0)


class TestWalkForward(unittest.TestCase):
    def test_fold_count_and_purge(self):
        folds = sl.walk_forward_splits(100, train=40, test=20, purge=5)
        # fold0: train[0,40) purge5 test[45,65); fold1: train[20,60) test[65,85); fold2 test end105>100停
        self.assertEqual(len(folds), 2)
        self.assertEqual(folds[0]["train"], (0, 40))
        self.assertEqual(folds[0]["test"], (45, 65))          # purge=5 gap
        self.assertEqual(folds[0]["test"][0] - folds[0]["train"][1], 5)

    def test_no_fold_when_too_short(self):
        self.assertEqual(sl.walk_forward_splits(30, 40, 20), [])

    def test_bad_args(self):
        with self.assertRaises(ValueError):
            sl.walk_forward_splits(100, 0, 20)


class TestHoldout(unittest.TestCase):
    def test_frac(self):
        d = list(range(10))
        disc, hold = sl.holdout_split(d, holdout_frac=0.3)
        self.assertEqual(disc, list(range(7)))
        self.assertEqual(hold, [7, 8, 9])

    def test_from_date(self):
        d = ["2024-01", "2024-06", "2025-01", "2025-06"]
        disc, hold = sl.holdout_split(d, holdout_from="2025-01")
        self.assertEqual(disc, ["2024-01", "2024-06"])
        self.assertEqual(hold, ["2025-01", "2025-06"])

    def test_leak_assertion(self):
        with self.assertRaises(AssertionError):
            sl.assert_no_holdout_leak(["2025-06"], ["2025-01", "2025-06"])
        self.assertTrue(sl.assert_no_holdout_leak(["2024-01"], ["2025-06"]))


class TestBlockBootstrap(unittest.TestCase):
    def test_significant_positive(self):
        # 均值 0.05 明显 > null 0.0 → p 很小
        r = sl.block_bootstrap_pvalue([0.05] * 40, null_mean=0.0, seed=1)
        self.assertLess(r["p_value"], 0.05)

    def test_not_significant(self):
        # 有方差、均值≈null(0.01) → 自助均值跨 null 两侧 → p 约 0.5,不显著
        r = sl.block_bootstrap_pvalue([0.0, 0.02] * 20, null_mean=0.01, seed=1)
        self.assertGreater(r["p_value"], 0.1)

    def test_deterministic_seed(self):
        a = sl.block_bootstrap_pvalue([0.02, -0.01, 0.03] * 10, null_mean=0.0, seed=7)
        b = sl.block_bootstrap_pvalue([0.02, -0.01, 0.03] * 10, null_mean=0.0, seed=7)
        self.assertEqual(a["p_value"], b["p_value"])          # 同 seed 可复现

    def test_empty(self):
        self.assertEqual(sl.block_bootstrap_pvalue([], seed=0)["p_value"], 1.0)


class TestBenjaminiHochberg(unittest.TestCase):
    def test_known(self):
        r = sl.benjamini_hochberg([0.001, 0.01, 0.04, 0.2, 0.5], alpha=0.05)
        # 排序后 rank/m*alpha: .01/.02/.03/.04/.05;最大满足 p<=阈 的是 rank2(0.01<=0.02)
        self.assertEqual(r["n_reject"], 2)
        self.assertEqual(r["rejected"], [True, True, False, False, False])

    def test_none_reject(self):
        r = sl.benjamini_hochberg([0.5, 0.6, 0.9], alpha=0.05)
        self.assertEqual(r["n_reject"], 0)

    def test_empty(self):
        self.assertEqual(sl.benjamini_hochberg([])["n_reject"], 0)


class TestSidakSharpe(unittest.TestCase):
    def test_norm_cdf(self):
        self.assertAlmostEqual(sl._norm_cdf(0), 0.5, places=6)
        self.assertAlmostEqual(sl._norm_cdf(1.6449), 0.95, places=3)

    def test_sidak_monotonic(self):
        # 试验越多,同一 Sharpe 的 Šidák 校正 p 越大(越不显著)
        p1 = sl.sidak_adjusted_sharpe_pvalue(0.25, 104, n_trials=1)["p_sidak"]
        p20 = sl.sidak_adjusted_sharpe_pvalue(0.25, 104, n_trials=20)["p_sidak"]
        self.assertGreater(p20, p1)

    def test_backcompat_alias(self):
        # 旧名保留为别名,且旧 key p_deflated 仍在
        self.assertIs(sl.deflated_sharpe_pvalue, sl.sidak_adjusted_sharpe_pvalue)
        self.assertIn("p_deflated", sl.sidak_adjusted_sharpe_pvalue(0.25, 104, 1))

    def test_tstat_zero_obs(self):
        self.assertEqual(sl.sharpe_tstat(1.0, 1), 0.0)


class TestCoverageVerdict(unittest.TestCase):
    def test_no_denominator_is_unknown(self):
        # 无分母 → coverage-unknown,不能通过(评审#6:1命中不等于覆盖)
        r = sl.coverage_verdict(["600519", "000001"], delisting_symbols=["LEHMQ"])
        self.assertFalse(r["trustworthy"])
        self.assertIsNone(r["survivorship_coverage"])
        self.assertTrue(any("coverage-unknown" in f for f in r["flags"]))

    def test_partial_coverage_fails(self):
        # 分母2、命中1 → 覆盖50%<80% → 不可信
        r = sl.coverage_verdict(["A"], delisting_symbols=["X"], expected_delisted=["X", "Y"])
        self.assertFalse(r["trustworthy"])
        self.assertAlmostEqual(r["survivorship_coverage"], 0.5)

    def test_pit_coverage_flag(self):
        r = sl.coverage_verdict(["A", "B"], delisting_symbols=["X", "Y"],
                                expected_delisted=["X", "Y"], pit_covered_symbols=["A"])
        # 幸存者覆盖100%达标,但 PIT 50%<80% → 前视旗 → 不可信
        self.assertFalse(r["trustworthy"])
        self.assertTrue(any("lookahead" in f for f in r["flags"]))

    def test_trustworthy_needs_full_coverage(self):
        r = sl.coverage_verdict(["A", "B"], delisting_symbols=["X", "Y"],
                                expected_delisted=["X", "Y"], pit_covered_symbols=["A", "B"])
        self.assertTrue(r["trustworthy"])
        self.assertEqual(r["survivorship_coverage"], 1.0)


class TestTrialLedger(unittest.TestCase):
    def test_record_load_count(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "trials.jsonl")
            sl.record_trial({"signal": "rsi", "split": "train", "edge": 0.02}, p)
            sl.record_trial({"signal": "gc", "split": "holdout", "edge": -0.01}, p)
            self.assertEqual(sl.trial_count(p), 2)
            self.assertEqual(sl.trial_count(p, split="train"), 1)
            self.assertEqual(len(sl.load_trials(p)), 2)

    def test_count_missing_file(self):
        self.assertEqual(sl.trial_count("/tmp/nonexistent_trials_xyz.jsonl"), 0)


if __name__ == "__main__":
    unittest.main()
