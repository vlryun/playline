"""Streamlit 화면 동작 테스트 (AppTest, 브라우저 없이 실행).

데모 데이터로 화면 흐름을 확인한다. 파일 업로드 위젯은 AppTest에서 조작할 수 없으므로
업로드·분석은 브라우저에서 따로 확인한다.
"""

import json
import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest

from playline.storage import parse_project

APP = str(Path(__file__).resolve().parent.parent / "app.py")


def fresh():
    at = AppTest.from_file(APP, default_timeout=120)
    at.run()
    return at


class AppFlowTest(unittest.TestCase):
    def test_empty_start(self):
        at = fresh()
        self.assertEqual(len(at.exception), 0, [e.value for e in at.exception])
        self.assertIsNone(at.session_state.ws)
        self.assertTrue(at.button(key="arrange_btn").disabled)

    def test_library_flow(self):
        from playline.library import load_library
        lib = load_library()
        if not lib:
            self.skipTest("라이브러리가 비어 있음")
        at = fresh()
        self.assertTrue(at.button(key="lib_start").disabled)
        at.button(key="lib_all").click().run()
        at.button(key="lib_start").click().run()
        self.assertEqual(len(at.exception), 0, [e.value for e in at.exception])
        ws = at.session_state.ws
        self.assertEqual(ws["kind"], "measured")
        self.assertEqual(len(ws["original"]), len(lib))
        self.assertTrue(all(t["source"] == "library" for t in ws["tracks"].values()))
        self.assertIsNotNone(ws["suggested"])
        # 분석값은 라이브러리 파일 값 그대로 (다시 분석하지 않음)
        self.assertEqual(at.session_state.analysis_runs, 0)

    def test_library_add_again_no_duplicate_and_replace(self):
        from playline.library import load_library
        lib = load_library()
        if len(lib) < 2:
            self.skipTest("라이브러리 곡이 2곡 미만")
        at = fresh()
        at.button(key="lib_all").click().run()
        at.button(key="lib_start").click().run()
        ws = at.session_state.ws
        self.assertEqual(len(ws["original"]), len(lib))
        # 작업 중에는 '추가' 버튼, 같은 곡을 다시 추가해도 중복되지 않음
        at.button(key="lib_all").click().run()
        self.assertIn("추가", at.button(key="lib_start").label)
        at.button(key="lib_start").click().run()
        self.assertEqual(len(at.session_state.ws["original"]), len(lib))
        # 바꾸기: 한 곡만 고르면 그 곡만 남는다
        first = lib[0]["sha256"][:12]
        at.checkbox(key=f"lib_pick_{first}").check().run()
        at.button(key="lib_replace").click().run()
        self.assertEqual(at.session_state.ws["original"], [first])

    def test_remove_keeps_other_values(self):
        from playline.library import load_library
        lib = load_library()
        if len(lib) < 2:
            self.skipTest("라이브러리 곡이 2곡 미만")
        at = fresh()
        at.button(key="lib_all").click().run()
        at.button(key="lib_start").click().run()
        ws = at.session_state.ws
        keep, drop = ws["original"][0], ws["original"][1]
        ws["tracks"][keep]["bpm_factor"] = 0.5
        at.button(key=f"rm_{drop}").click().run()
        self.assertEqual(len(at.exception), 0, [e.value for e in at.exception])
        ws = at.session_state.ws
        self.assertNotIn(drop, ws["tracks"])
        self.assertEqual(ws["tracks"][keep]["bpm_factor"], 0.5)
        self.assertNotIn(drop, ws["current"])

    def test_all_nine_flows_keep_pins(self):
        from playline.arrange import MODES
        self.assertEqual(list(MODES), ["rise", "fall", "arc", "valley", "wave", "early", "finale", "plateau", "workout"])
        at = fresh()
        at.button(key="hero_demo").click().run()
        ws = at.session_state.ws
        first, last = ws["original"][3], ws["original"][7]
        at.selectbox(key="pin_first").select(first).run()
        at.selectbox(key="pin_last").select(last).run()
        for mode in MODES:
            at.button(key=f"mode_btn_{mode}").click().run()
            at.button(key="arrange_btn").click().run()
            self.assertEqual(len(at.exception), 0, [e.value for e in at.exception])
            cur = at.session_state.ws["current"]
            self.assertEqual(at.session_state.mode, mode)
            self.assertEqual(cur[0], first, mode)
            self.assertEqual(cur[-1], last, mode)
            self.assertEqual(sorted(cur), sorted(ws["original"]))

    def test_result_summary_states(self):
        import html as _h

        def summary(at):
            boxes = [x.proto.body for x in at.get("html") if 'class="pl-summary' in x.proto.body]
            return _h.unescape(boxes[0]) if boxes else ""

        at = fresh()
        at.button(key="hero_demo").click().run()
        for mode, label in (("rise", "점점 신나게"), ("wave", "파도처럼")):
            at.button(key=f"mode_btn_{mode}").click().run()
            # 설정만 바꾸고 아직 다시 추천하지 않음 → 예전 숫자 대신 안내
            if mode != "rise":
                self.assertIn("설정이 바뀌었어요. 다시 추천해 주세요", summary(at))
                self.assertNotIn("정렬했어요", summary(at))
            at.button(key="arrange_btn").click().run()
            text = summary(at)
            self.assertIn(f"‘{label}’ 흐름으로 정렬했어요", text)
            ws = at.session_state.ws
            from playline import arrange as ar, storage
            sc = ar.compute_scores([{"id": t, "bpm": storage.effective_bpm(ws["tracks"][t]), "rms": ws["tracks"][t]["rms"]}
                                    for t in ws["original"]], 0.5)
            o = ar.evaluate(ws["original"], sc, mode).mae
            sg = ar.evaluate(ws["suggested"], sc, mode).mae
            self.assertIn(f"{o:.3f}", text)
            self.assertIn(f"{sg:.3f}", text)
            self.assertIn(ar.change_word(o, sg), text)
            self.assertNotIn("지금 순서(직접 바꿈)", text)
        # 직접 순서를 바꾸면 추천 결과와 지금 순서 결과를 따로 보여 준다
        ws = at.session_state.ws
        at.button(key=f"down_{ws['current'][0]}").click().run()
        text = summary(at)
        self.assertIn("‘파도처럼’ 흐름으로 정렬했어요", text)
        self.assertIn("지금 순서(직접 바꿈)", text)

    def test_demo_flow(self):
        at = fresh()
        at.button(key="hero_demo").click().run()
        self.assertEqual(len(at.exception), 0, [e.value for e in at.exception])
        ws = at.session_state.ws
        self.assertEqual(ws["kind"], "demo")
        n = len(ws["original"])
        self.assertGreaterEqual(n, 10)
        self.assertEqual(sorted(ws["suggested"]), sorted(ws["original"]))
        self.assertEqual(ws["current"], ws["suggested"])
        # 데모는 재생 버튼이 모두 비활성
        for tid in ws["original"]:
            self.assertTrue(at.button(key=f"play_{tid}").disabled)

        # 모드 바꾸고 재배열 → 결정적 결과
        at.button(key="mode_btn_arc").click().run()
        self.assertEqual(at.session_state.mode, "arc")
        at.button(key="arrange_btn").click().run()
        arc1 = list(at.session_state.ws["suggested"])
        at.button(key="arrange_btn").click().run()
        self.assertEqual(at.session_state.ws["suggested"], arc1)

        # 수동 이동 → 현재 순서 변경, 제안은 유지
        first, second = arc1[0], arc1[1]
        at.button(key=f"down_{first}").click().run()
        ws = at.session_state.ws
        self.assertEqual(ws["current"][:2], [second, first])
        self.assertEqual(ws["suggested"], arc1)
        self.assertEqual(sorted(ws["current"]), sorted(ws["original"]))

        # 제안 순서로 복구
        at.button(key="hero_demo")  # 존재 확인
        restore = [b for b in at.button if b.label == "추천 순서로 되돌리기"][0]
        restore.click().run()
        self.assertEqual(at.session_state.ws["current"], arc1)

        # 원본 복구
        [b for b in at.button if b.label == "원래 순서로 되돌리기"][0].click().run()
        self.assertEqual(at.session_state.ws["current"], at.session_state.ws["original"])

    def test_pins_and_lock(self):
        at = fresh()
        at.button(key="hero_demo").click().run()
        ids = at.session_state.ws["original"]
        at.selectbox(key="pin_first").set_value(ids[3]).run()
        at.selectbox(key="pin_last").set_value(ids[0]).run()
        self.assertEqual(at.session_state.ws["current"][0], ids[3])
        self.assertEqual(at.session_state.ws["current"][-1], ids[0])
        at.button(key="arrange_btn").click().run()
        cur = at.session_state.ws["current"]
        self.assertEqual((cur[0], cur[-1]), (ids[3], ids[0]))
        # 잠긴 곡의 이동 버튼과, 잠긴 자리로 들어가는 버튼은 비활성
        self.assertTrue(at.button(key=f"down_{cur[0]}").disabled)
        self.assertTrue(at.button(key=f"up_{cur[1]}").disabled)
        self.assertTrue(at.button(key=f"up_{cur[-1]}").disabled)
        self.assertTrue(at.button(key=f"down_{cur[-2]}").disabled)
        # 같은 곡을 양쪽에 고정 → 오류 안내, 자동 배열 비활성
        at.selectbox(key="pin_last").set_value(ids[3]).run()
        self.assertTrue(any("동시에" in e.value for e in at.error))
        self.assertTrue(at.button(key="arrange_btn").disabled)

    def test_versions_and_export(self):
        at = fresh()
        at.button(key="hero_demo").click().run()
        sug = list(at.session_state.ws["suggested"])
        at.text_input(key="version_name").input("제안안").run()
        [b for b in at.button if b.label == "현재 순서 저장"][0].click().run()
        self.assertEqual(at.session_state.ws["versions"][0]["name"], "제안안")
        at.button(key=f"down_{sug[0]}").click().run()
        self.assertNotEqual(at.session_state.ws["current"], sug)
        [b for b in at.button if b.label == "불러오기"][0].click().run()
        self.assertEqual(at.session_state.ws["current"], sug)
        self.assertEqual(len(at.exception), 0, [e.value for e in at.exception])

    def test_settings_change_does_not_reset(self):
        at = fresh()
        at.button(key="hero_demo").click().run()
        sug = list(at.session_state.ws["suggested"])
        at.button(key=f"down_{sug[2]}").click().run()
        cur = list(at.session_state.ws["current"])
        at.slider(key="bpm_weight_pct").set_value(80).run()
        self.assertEqual(at.session_state.ws["current"], cur)  # 설정만 바꿔서는 편집 순서 유지
        self.assertEqual(at.session_state.analysis_runs, 0)


class ExportFormatTest(unittest.TestCase):
    def test_json_from_demo_session_is_valid(self):
        from playline.demo import load_demo
        from playline.storage import to_json
        _, tr = load_demo()
        tracks = {t["id"]: t for t in tr}
        ids = list(tracks)
        raw = to_json(tracks=tracks, original=ids, suggested=ids[::-1], current=ids[::-1],
                      settings={"mode": "arc", "bpm_weight": 0.5, "smooth": 0.2, "pin_first": None, "pin_last": None},
                      versions=[], data_kind="demo")
        self.assertIn("음원이 포함되어 있지 않습니다", json.loads(raw)["note"])
        self.assertEqual(parse_project(raw)[1], [])


if __name__ == "__main__":
    unittest.main()
