# [AI 보조 도구: Claude Code (Claude Opus 5.5), 작업: '라이브러리 로드·변환 테스트']
import json
import tempfile
import unittest
from pathlib import Path

from playline import library, storage

SHA = "a" * 64


class LibraryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.path = self.tmp / "library.json"
        self.audio = self.tmp / "audio"
        self.audio.mkdir()

    def test_load_and_to_track(self):
        library.save_library([{"title": "B", "filename": "b.mp3", "sha256": SHA, "size_bytes": 3,
                               "duration_sec": 10.0, "bpm": 120.0, "rms": 0.1},
                              {"title": "bad", "sha256": None, "rms": 0.1}], self.path)
        entries = library.load_library(self.path)
        self.assertEqual(len(entries), 1)  # 해시 없는 항목은 버림
        t = library.to_track(entries[0])
        self.assertEqual(t["id"], SHA[:12])
        self.assertEqual(t["source"], "library")
        self.assertEqual(t["bpm_alternatives"], [60.0, 240.0])

    def test_missing_file_gives_empty(self):
        self.assertEqual(library.load_library(self.tmp / "none.json"), [])

    def test_audio_files_requires_same_size(self):
        e = {"filename": "b.mp3", "sha256": SHA, "size_bytes": 3}
        (self.audio / "b.mp3").write_bytes(b"abc")
        self.assertIn(SHA, library.audio_files([e], self.audio))
        (self.audio / "b.mp3").write_bytes(b"abcd")
        self.assertNotIn(SHA, library.audio_files([e], self.audio))

    def test_search(self):
        es = [{"title": "Zombie", "artist": None}, {"title": "Nostalgia", "artist": "X"}]
        self.assertEqual([e["title"] for e in library.search(es, "zom")], ["Zombie"])
        self.assertEqual(len(library.search(es, "")), 2)

    def test_json_roundtrip_keeps_library_source(self):
        t = library.to_track({"title": "B", "filename": "b.mp3", "sha256": SHA, "bpm": 100.0, "rms": 0.2})
        raw = storage.to_json(tracks={t["id"]: t}, original=[t["id"]], suggested=None, current=[t["id"]],
                              settings={"mode": "rise", "bpm_weight": 0.5, "smooth": 0.2,
                                        "pin_first": None, "pin_last": None},
                              versions=[], data_kind="measured")
        project, errs = storage.parse_project(raw if isinstance(raw, (bytes, str)) else json.dumps(raw))
        self.assertFalse(errs, errs)
        self.assertEqual(project["tracks"][t["id"]]["source"], "library")


class RealLibraryFileTest(unittest.TestCase):
    def test_repo_library_is_valid(self):
        for e in library.load_library():
            self.assertRegex(e["sha256"], r"^[0-9a-f]{64}$")
            self.assertGreater(e["rms"], 0)


if __name__ == "__main__":
    unittest.main()
