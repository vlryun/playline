"""저장·불러오기 테스트."""

import csv
import io
import json
import unittest

from playline.arrange import compute_scores
from playline.demo import load_demo
from playline.storage import match_audio, parse_project, to_csv, to_json

SHA_A = "a" * 64
SHA_B = "b" * 64


def sample_tracks():
    return {
        "x1": {"id": "x1", "title": "노을 산책", "artist": None, "filename": "노을 산책.mp3",
               "sha256": SHA_A, "size_bytes": 10, "duration_sec": 200.0, "bpm_raw": 90.0,
               "bpm_factor": 1.0, "rms": 0.1, "status": "ok", "category": None, "bpm_alternatives": [45, 180]},
        "x2": {"id": "x2", "title": "Night Drive", "artist": None, "filename": "Night Drive.wav",
               "sha256": SHA_B, "size_bytes": 20, "duration_sec": 180.0, "bpm_raw": None,
               "bpm_factor": 1.0, "rms": 0.2, "status": "bpm_failed", "category": None, "bpm_alternatives": []},
    }


SETTINGS = {"mode": "rise", "bpm_weight": 0.5, "smooth": 0.2, "pin_first": None, "pin_last": None}


def export(**over):
    kw = dict(tracks=sample_tracks(), original=["x1", "x2"], suggested=["x2", "x1"], current=["x2", "x1"],
              settings=dict(SETTINGS),
              versions=[{"name": "v1", "created_at": "t", "order": ["x1", "x2"], "settings": dict(SETTINGS)}],
              data_kind="measured")
    kw.update(over)
    return to_json(**kw)


class JsonRoundTrip(unittest.TestCase):
    def test_roundtrip(self):
        proj, errs = parse_project(export())
        self.assertEqual(errs, [])
        self.assertEqual(proj["current"], ["x2", "x1"])
        self.assertEqual(proj["tracks"]["x1"]["title"], "노을 산책")
        self.assertEqual(len(proj["versions"]), 1)
        self.assertNotIn("audio", json.loads(export()))

    def bad(self, mutate):
        d = json.loads(export())
        mutate(d)
        proj, errs = parse_project(json.dumps(d).encode())
        self.assertIsNone(proj)
        self.assertTrue(errs)
        return errs

    def test_invalid_cases(self):
        self.assertTrue(parse_project(b"{not json")[1])
        self.assertTrue(parse_project(b"\xff\xfe\x00")[1])
        self.assertTrue(parse_project(b"[]")[1])
        self.bad(lambda d: d.update(app="OTHER"))
        self.bad(lambda d: d.update(schema_version=99))
        self.bad(lambda d: d.update(tracks=[]))
        self.bad(lambda d: d["tracks"][0].update(rms="loud"))
        self.bad(lambda d: d["tracks"][0].update(rms=-1))
        self.bad(lambda d: d["tracks"][0].update(bpm_raw=0))
        self.bad(lambda d: d["tracks"][0].update(sha256="abc"))
        self.bad(lambda d: d["tracks"][1].update(id="x1"))
        self.bad(lambda d: d["orders"].update(current=["x1", "x1"]))
        self.bad(lambda d: d["orders"].update(original=["x1"]))
        self.bad(lambda d: d["settings"].update(mode="random"))
        self.bad(lambda d: d["settings"].update(bpm_weight=3))
        self.bad(lambda d: d["settings"].update(pin_first="x1", pin_last="x1"))
        self.bad(lambda d: d["versions"][0].update(order=["x1", "zz"]))

    def test_demo_without_hash_ok(self):
        meta, tr = load_demo()
        tracks = {t["id"]: t for t in tr}
        ids = list(tracks)
        raw = to_json(tracks=tracks, original=ids, suggested=None, current=ids, settings=dict(SETTINGS),
                      versions=[], data_kind="demo")
        proj, errs = parse_project(raw)
        self.assertEqual(errs, [])
        self.assertEqual(proj["data_kind"], "demo")


class CsvTest(unittest.TestCase):
    def test_csv(self):
        tr = sample_tracks()
        sc = compute_scores([{"id": k, "bpm": v["bpm_raw"], "rms": v["rms"]} for k, v in tr.items()], 0.5)
        raw = to_csv(["x2", "x1"], tr, sc)
        self.assertTrue(raw.startswith("﻿".encode("utf-8")))
        rows = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"))))
        self.assertEqual(rows[0][:6], ["순서", "곡명", "아티스트", "출처", "파일명", "길이(초)"])
        self.assertEqual(rows[1][1], "Night Drive")
        self.assertEqual(rows[1][7], "")  # BPM 추정 실패는 빈칸
        self.assertEqual(rows[2][1], "노을 산책")
        self.assertEqual(rows[2][7], "90.0")


class MatchTest(unittest.TestCase):
    def test_hash_not_name(self):
        tr = sample_tracks()
        uploads = {SHA_A: {"filename": "다른이름.mp3"}, "c" * 64: {"filename": "Night Drive.wav"}}
        m = match_audio(tr, uploads)
        self.assertEqual(m["linked"], {"x1": SHA_A})
        self.assertEqual(m["missing"], ["x2"])  # 이름이 같아도 해시가 다르면 연결 안 함
        self.assertEqual(m["extra"], ["c" * 64])
        self.assertEqual(m["renamed"], [("x1", "다른이름.mp3")])


if __name__ == "__main__":
    unittest.main()


class SchemaV2Test(unittest.TestCase):
    def test_v1_file_still_loads(self):
        data = json.loads(export())
        data["schema_version"] = 1
        for t in data["tracks"]:
            t.pop("source", None)
            t.pop("analysis_scope", None)
        project, errs = parse_project(json.dumps(data).encode("utf-8"))
        self.assertFalse(errs, errs)
        self.assertTrue(all(t["source"] == "upload" for t in project["tracks"].values()))
        self.assertTrue(all(t["analysis_scope"] == "full" for t in project["tracks"].values()))

    def test_mixed_sources_roundtrip(self):
        tr = sample_tracks()
        tr["x1"]["source"] = "library"
        tr["x2"]["source"] = "upload"
        raw = to_json(tracks=tr, original=["x1", "x2"], suggested=["x2", "x1"], current=["x2", "x1"],
                      settings={**SETTINGS, "mode": "wave", "pin_first": "x2"}, versions=[], data_kind="measured")
        data = json.loads(raw)
        self.assertEqual(data["schema_version"], 2)
        project, errs = parse_project(raw)
        self.assertFalse(errs, errs)
        self.assertEqual(project["tracks"]["x1"]["source"], "library")
        self.assertEqual(project["tracks"]["x2"]["source"], "upload")
        self.assertEqual(project["settings"]["mode"], "wave")
        self.assertEqual(project["settings"]["pin_first"], "x2")

    def test_unknown_future_version_rejected(self):
        data = json.loads(export())
        data["schema_version"] = 99
        _, errs = parse_project(json.dumps(data).encode("utf-8"))
        self.assertTrue(errs)


class CurveSettingsTest(unittest.TestCase):
    def test_curve_saved_and_restored(self):
        curve = [[0, .2], [0.5, .9], [1, .1]]
        st = {**SETTINGS, "mode": "custom", "curve": curve}
        raw = export(settings=st, versions=[{"name": "v", "created_at": "t", "order": ["x1", "x2"], "settings": st}])
        project, errs = parse_project(raw)
        self.assertFalse(errs, errs)
        self.assertEqual(project["settings"]["curve"], curve)
        self.assertEqual(project["versions"][0]["settings"]["curve"], curve)

    def test_custom_without_curve_rejected_and_bad_curve_rejected(self):
        for bad in ({**SETTINGS, "mode": "custom"}, {**SETTINGS, "mode": "custom", "curve": [[0, 0], [0, 1]]}):
            _, errs = parse_project(export(settings=bad))
            self.assertTrue(errs)

    def test_old_file_without_curve_still_opens(self):
        project, errs = parse_project(export())
        self.assertFalse(errs, errs)
        self.assertIsNone(project["settings"].get("curve"))
