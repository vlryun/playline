"""자동 배열 로직 테스트 (합성 데이터 사용, 실제 음악 검증 아님)."""

import itertools
import unittest

import numpy as np

from playline.arrange import (MODES, arrange, compute_scores, evaluate, move, normalize,
                              target_curve, target_shape, apply_pins)


def make(bpms, rmss):
    return [{"id": f"t{i}", "bpm": b, "rms": r} for i, (b, r) in enumerate(zip(bpms, rmss))]


class NormalizeTest(unittest.TestCase):
    def test_minmax(self):
        self.assertEqual(normalize([1, 2, 3]), [0.0, 0.5, 1.0])

    def test_all_equal(self):
        self.assertEqual(normalize([5, 5, 5]), [0.5, 0.5, 0.5])

    def test_none(self):
        self.assertEqual(normalize([None, 2, 4]), [None, 0.0, 1.0])
        self.assertEqual(normalize([None, None]), [None, None])


class TargetTest(unittest.TestCase):
    def test_shapes(self):
        np.testing.assert_allclose(target_shape("rise", 5), [0, .25, .5, .75, 1])
        np.testing.assert_allclose(target_shape("fall", 5), [1, .75, .5, .25, 0])
        arc = target_shape("arc", 11)
        self.assertAlmostEqual(arc[0], 0)
        self.assertAlmostEqual(arc[-1], 0)
        self.assertAlmostEqual(arc.max(), 1)
        self.assertEqual(int(np.argmax(arc)), 6)  # 60% 지점
        self.assertTrue(all(np.diff(arc[:7]) > 0) and all(np.diff(arc[6:]) < 0))

    def test_range_mapping(self):
        np.testing.assert_allclose(target_curve("rise", 3, 0.2, 0.8), [0.2, 0.5, 0.8])
        np.testing.assert_allclose(target_curve("rise", 3, 0.4, 0.4), [0.4, 0.4, 0.4])

    def test_single(self):
        self.assertEqual(len(target_curve("arc", 1, 0, 1)), 1)


class ArrangeTest(unittest.TestCase):
    def setUp(self):
        self.tracks = make([90, 140, 70, 120, 100, 160, 80],
                           [0.10, 0.25, 0.05, 0.20, 0.15, 0.30, 0.08])
        self.order = [t["id"] for t in self.tracks]
        self.scores = compute_scores(self.tracks, 0.5)

    def seq(self, order):
        return [self.scores[t].score for t in order]

    def test_permutation_all_modes(self):
        for mode in MODES:
            for smooth in (0, 0.2, 1.0):
                r = arrange(self.order, self.scores, mode, smooth=smooth)
                self.assertIsNone(r.error)
                self.assertEqual(sorted(r.order), sorted(self.order))
                self.assertEqual(len(r.order), len(set(r.order)))

    def test_rise_fall_monotonic(self):
        s = self.seq(arrange(self.order, self.scores, "rise").order)
        self.assertEqual(s, sorted(s))
        s = self.seq(arrange(self.order, self.scores, "fall").order)
        self.assertEqual(s, sorted(s, reverse=True))

    def test_arc_peak_in_middle(self):
        s = self.seq(arrange(self.order, self.scores, "arc").order)
        peak = int(np.argmax(s))
        self.assertTrue(0 < peak < len(s) - 1)
        self.assertLess(s[0], s[peak])
        self.assertLess(s[-1], s[peak])

    def test_improves_mae(self):
        for mode in MODES:
            r = arrange(self.order, self.scores, mode, smooth=0)
            self.assertLessEqual(evaluate(r.order, self.scores, mode).mae,
                                 evaluate(self.order, self.scores, mode).mae + 1e-12)

    def test_optimal_mae_bruteforce(self):
        # smooth=0이면 목표 오차 합이 모든 순열 중 최소여야 한다 (7곡 = 5040 순열)
        for mode in MODES:
            r = arrange(self.order, self.scores, mode, smooth=0)
            best = min(evaluate(list(p), self.scores, mode).mae
                       for p in itertools.permutations(self.order))
            self.assertAlmostEqual(evaluate(r.order, self.scores, mode).mae, best, places=10)

    def test_deterministic(self):
        a = arrange(self.order, self.scores, "arc", smooth=0.3).order
        for _ in range(5):
            self.assertEqual(arrange(self.order, self.scores, "arc", smooth=0.3).order, a)

    def test_pins(self):
        r = arrange(self.order, self.scores, "rise", pin_first="t5", pin_last="t2")
        self.assertEqual(r.order[0], "t5")
        self.assertEqual(r.order[-1], "t2")
        self.assertEqual(sorted(r.order), sorted(self.order))
        rest = self.seq(r.order[1:-1])
        self.assertEqual(rest, sorted(rest))

    def test_pin_conflict(self):
        r = arrange(self.order, self.scores, "rise", pin_first="t1", pin_last="t1")
        self.assertIsNone(r.order)
        self.assertIn("동시에", r.error)

    def test_pin_unknown(self):
        r = arrange(self.order, self.scores, "rise", pin_first="zzz")
        self.assertIsNone(r.order)

    def test_single_track(self):
        tr = make([100], [0.1])
        sc = compute_scores(tr, 0.5)
        r = arrange(["t0"], sc, "arc", pin_first="t0", pin_last="t0")
        self.assertEqual(r.order, ["t0"])
        m = evaluate(["t0"], sc, "arc")
        self.assertEqual(m.mae, 0.0)

    def test_two_tracks_both_pinned(self):
        tr = make([100, 120], [0.1, 0.2])
        sc = compute_scores(tr, 0.5)
        r = arrange(["t0", "t1"], sc, "rise", pin_first="t1", pin_last="t0")
        self.assertEqual(r.order, ["t1", "t0"])

    def test_all_equal_keeps_original(self):
        tr = make([100] * 4, [0.2] * 4)
        sc = compute_scores(tr, 0.5)
        order = [t["id"] for t in tr]
        r = arrange(order, sc, "arc")
        self.assertEqual(r.order, order)
        self.assertTrue(any("같아" in n for n in r.notes))

    def test_bpm_missing(self):
        tr = make([None, 120, 90], [0.3, 0.1, 0.2])
        sc = compute_scores(tr, 0.5)
        self.assertEqual(sc["t0"].basis, "RMS만")
        self.assertAlmostEqual(sc["t0"].score, 1.0)
        r = arrange([t["id"] for t in tr], sc, "rise")
        self.assertEqual(sorted(r.order), ["t0", "t1", "t2"])

    def test_all_bpm_missing(self):
        tr = make([None, None], [0.3, 0.1])
        sc = compute_scores(tr, 0.7)
        self.assertEqual(arrange(["t0", "t1"], sc, "rise").order, ["t1", "t0"])

    def test_weights(self):
        tr = make([60, 180], [0.3, 0.1])
        self.assertEqual(arrange(["t0", "t1"], compute_scores(tr, 1.0), "rise").order, ["t0", "t1"])
        self.assertEqual(arrange(["t0", "t1"], compute_scores(tr, 0.0), "rise").order, ["t1", "t0"])

    def test_same_normalization_for_all_orders(self):
        # 같은 scores 객체를 쓰므로 원본·제안 순서의 개별 점수는 동일해야 한다
        r = arrange(self.order, self.scores, "rise")
        self.assertEqual(sorted(self.seq(self.order)), sorted(self.seq(r.order)))

    def test_move_and_lock(self):
        o = ["a", "b", "c", "d"]
        self.assertEqual(move(o, 1, 1, set()), ["a", "c", "b", "d"])
        self.assertEqual(move(o, 1, -1, {0}), o)  # 잠긴 첫 자리로 이동 불가
        self.assertEqual(move(o, 3, -1, {3}), o)  # 잠긴 곡은 이동 불가
        self.assertEqual(move(o, 0, -1, set()), o)

    def test_apply_pins(self):
        self.assertEqual(apply_pins(["a", "b", "c", "d"], "c", "a"), ["c", "b", "d", "a"])
        self.assertEqual(apply_pins(["a", "b"], None, None), ["a", "b"])


if __name__ == "__main__":
    unittest.main()


class ModeShapeTest(unittest.TestCase):
    def test_all_modes_in_range_and_distinct(self):
        shapes = {m: target_shape(m, 21) for m in MODES}
        self.assertGreaterEqual(len(MODES), 5)
        for m, s in shapes.items():
            self.assertTrue(np.all((s >= -1e-9) & (s <= 1 + 1e-9)), m)
        keys = list(shapes)
        for i in range(len(keys)):
            for j in range(i + 1, len(keys)):
                self.assertFalse(np.allclose(shapes[keys[i]], shapes[keys[j]]), (keys[i], keys[j]))

    def test_shape_features(self):
        w = target_shape("wave", 41)
        self.assertAlmostEqual(w[10], 1.0)   # 25% 지점 첫 정점
        self.assertAlmostEqual(w[20], 0.0)   # 50% 지점 골
        v = target_shape("valley", 21)
        self.assertEqual(int(np.argmin(v)), 10)
        f = target_shape("finale", 11)
        self.assertLess(f[7], 0.4)
        self.assertEqual(f[-1], 1.0)
        self.assertEqual(int(np.argmax(target_shape("early", 21))), 4)
