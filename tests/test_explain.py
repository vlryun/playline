# [AI 보조 도구: Claude Code (Claude Opus 5.5), 작업: "'왜 여기에?' 설명 검증"]
import unittest

from playline.arrange import MODES, arrange, compute_scores, score_range, target_curve
from playline.explain import iyo, placement, section_text


def setup(mode="wave", curve=None, pins=(None, None), smooth=0.2):
    tracks = [{"id": f"t{i}", "bpm": b, "rms": r} for i, (b, r) in
              enumerate([(70, .05), (128, .2), (95, .1), (150, .25), (110, .12), (82, .07), (135, .18)])]
    sc = compute_scores(tracks, 0.5)
    org = [t["id"] for t in tracks]
    sug = arrange(org, sc, mode, *pins, smooth=smooth, curve=curve).order
    return tracks, sc, org, sug


def explain(tid, cur, org, sug, sc, mode="wave", curve=None, pins=(None, None), smooth=0.2, stale=False):
    return placement(tid, current=cur, original=org, suggested=sug, scores=sc, mode=mode, curve=curve,
                     pin_first=pins[0], pin_last=pins[1], smooth=smooth, bpm_weight=0.5, stale=stale,
                     bpm=100.0, rms=0.1)


class PlacementTest(unittest.TestCase):
    def test_numbers_match_sort_targets_for_all_modes(self):
        for mode in MODES:
            curve = [[0, .2], [.5, 1], [1, 0]] if mode == "custom" else None
            tracks, sc, org, sug = setup(mode, curve)
            lo, hi = score_range(sc)
            tgt = target_curve(mode, len(sug), lo, hi, curve)
            for i, tid in enumerate(sug):
                p = explain(tid, sug, org, sug, sc, mode, curve)
                self.assertEqual(p.pos, i + 1)
                self.assertAlmostEqual(p.target, float(tgt[i]))
                self.assertAlmostEqual(p.score, sc[tid].score)
                self.assertAlmostEqual(p.diff, abs(float(tgt[i]) - sc[tid].score))
                text = " ".join(p.lines)
                self.assertIn(f"{p.target:.3f}", text)
                self.assertIn(f"{p.score:.3f}", text)
                self.assertNotIn("최적", text + p.note)
                self.assertIn("비교한 정보", p.note)

    def test_movement_sentence(self):
        tracks, sc, org, sug = setup()
        tid = next(t for t in org if org.index(t) != sug.index(t))
        p = explain(tid, sug, org, sug, sc)
        self.assertIn(f"원래 {org.index(tid) + 1}번째였던 곡이 추천 순서에서는 {sug.index(tid) + 1}번째에 배치됐어요.",
                      p.lines)

    def test_pinned_first_and_last(self):
        pins = ("t2", "t5")
        tracks, sc, org, sug = setup(pins=pins)
        p = explain("t5", sug, org, sug, sc, pins=pins)
        self.assertTrue(p.lines[0].startswith("사용자가 마지막 곡으로 고정했어요"))
        p = explain("t2", sug, org, sug, sc, pins=pins)
        self.assertTrue(p.lines[0].startswith("사용자가 첫 곡으로 고정했어요"))

    def test_manual_order_keeps_three_orders_apart(self):
        tracks, sc, org, sug = setup()
        cur = list(sug)
        cur[1], cur[2] = cur[2], cur[1]
        tid = cur[1]
        p = explain(tid, cur, org, sug, sc)
        self.assertEqual(p.lines[0], "사용자가 직접 순서를 변경했어요. 아래는 현재 위치의 목표 점수와 곡의 점수 비교예요.")
        self.assertEqual(p.pos, 2)
        self.assertTrue(any(f"마지막 추천 {sug.index(tid) + 1}번째" in x and "지금 2번째(직접 바꾼 순서)" in x
                            for x in p.lines))

    def test_stale_shows_only_notice(self):
        tracks, sc, org, sug = setup()
        p = explain(sug[0], sug, org, sug, sc, stale=True)
        self.assertTrue(p.stale)
        self.assertEqual(p.lines, ["설정이 변경됐어요. 다시 추천하면 새 설정을 기준으로 배치 정보를 확인할 수 있어요."])

    def test_single_track_and_equal_scores(self):
        sc = compute_scores([{"id": "a", "bpm": 100, "rms": .1}], .5)
        p = explain("a", ["a"], ["a"], ["a"], sc, mode="rise")
        self.assertIn("한 곡뿐", " ".join(p.lines))
        sc = compute_scores([{"id": x, "bpm": 100, "rms": .1} for x in "abc"], .5)
        p = explain("b", list("abc"), list("abc"), list("abc"), sc, mode="arc")
        self.assertAlmostEqual(p.diff, 0.0)
        self.assertIn("모든 곡의 흐름 점수가 같아", p.note)

    def test_after_removal_explanations_follow_track_ids(self):
        tracks, sc, org, sug = setup()
        gone = sug[2]
        sc2 = compute_scores([t for t in tracks if t["id"] != gone], 0.5)
        org2 = [t for t in org if t != gone]
        sug2 = arrange(org2, sc2, "wave", smooth=0.2).order
        for tid in sug2:
            p = explain(tid, sug2, org2, sug2, sc2)
            self.assertEqual(p.pos, sug2.index(tid) + 1)
            self.assertAlmostEqual(p.score, sc2[tid].score)

    def test_section_words(self):
        self.assertIn("시작", section_text([0, .5, 1], 0))
        self.assertIn("마무리", section_text([0, .5, 1], 2))
        self.assertIn("올라가는", section_text([0, .5, 1], 1))
        self.assertIn("가장 높아지는", section_text([0, 1, 0], 1))
        self.assertIn("유지", section_text([.5, .5, .5], 1))
        self.assertEqual([iyo(x) for x in ("0.720", "0.725", "0.031")], ["이에요", "예요", "이에요"])


if __name__ == "__main__":
    unittest.main()
