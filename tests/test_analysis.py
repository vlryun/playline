"""음원 분석 테스트.

합성 신호(클릭 트랙, 무음, 잡음)와 깨진 파일로 예외 처리를 확인한다.
합성 신호는 계산 로직 검증용이며 실제 음악 분석 성능을 보여주지 않는다.
"""

import os
import tempfile
import unittest
from pathlib import Path

import numpy as np
import soundfile as sf

from playline.analysis import (SAMPLE_RATE, analyze_bytes, analyze_path, title_from_filename)


def wav_bytes(y, sr=SAMPLE_RATE):
    fd, p = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    try:
        sf.write(p, y, sr)
        return Path(p).read_bytes()
    finally:
        os.remove(p)


def click_track(bpm, seconds=20, sr=SAMPLE_RATE, amp=0.5):
    """일정 간격의 감쇠 잡음(드럼과 비슷한 타격음). 고정 시드라 매번 같은 신호."""
    rng = np.random.default_rng(0)
    y = np.zeros(int(seconds * sr), dtype=np.float32)
    period = int(round(60 / bpm * sr))
    L = 2000
    env = np.exp(-np.arange(L) / 300)
    for start in range(0, len(y) - L, period):
        y[start:start + L] += (amp * env * rng.standard_normal(L)).astype(np.float32)
    return np.clip(y, -1, 1)


class AnalysisTest(unittest.TestCase):
    def test_click_track_bpm(self):
        r = analyze_bytes(wav_bytes(click_track(120)), "클릭 120.wav")
        self.assertEqual(r.status, "ok", r.message)
        # 절반/두 배 추정 가능성을 허용
        self.assertTrue(any(abs(r.bpm * k - 120) < 4 for k in (0.5, 1, 2)), r.bpm)
        self.assertAlmostEqual(r.duration_sec, 20, delta=0.1)
        self.assertGreater(r.rms_mean, 0)
        self.assertEqual(len(r.sha256), 64)

    def test_silence(self):
        r = analyze_bytes(wav_bytes(np.zeros(SAMPLE_RATE * 5, dtype=np.float32)), "무음 파일.wav")
        self.assertEqual(r.status, "silent")
        self.assertIsNone(r.bpm)
        self.assertFalse(r.usable)

    def test_noise_without_beat_is_not_faked(self):
        # 일정한 사인파: 박자가 없음 → BPM 실패로 처리되거나, 추정되더라도 값을 꾸며내지 않음
        t = np.arange(SAMPLE_RATE * 8) / SAMPLE_RATE
        y = (0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
        r = analyze_bytes(wav_bytes(y), "sine.wav")
        self.assertIn(r.status, ("ok", "bpm_failed"))
        if r.status == "bpm_failed":
            self.assertIsNone(r.bpm)
            self.assertTrue(r.usable)

    def test_broken_file(self):
        r = analyze_bytes(b"this is not audio" * 100, "깨진 파일.mp3")
        self.assertEqual(r.status, "error")
        self.assertFalse(r.usable)

    def test_empty_and_wrong_ext(self):
        self.assertEqual(analyze_bytes(b"", "a.wav").status, "error")
        self.assertEqual(analyze_bytes(b"abc", "a.flac").status, "error")

    def test_korean_space_path(self):
        d = tempfile.mkdtemp(prefix="플레이 라인 ")
        p = Path(d) / "한글 이름 곡.wav"
        sf.write(p, click_track(100, 10), SAMPLE_RATE)
        try:
            r = analyze_path(p)
            self.assertEqual(r.filename, "한글 이름 곡.wav")
            self.assertIn(r.status, ("ok", "bpm_failed"))
        finally:
            p.unlink()
            os.rmdir(d)

    def test_temp_files_cleaned(self):
        before = set(Path(tempfile.gettempdir()).glob("playline_*"))
        analyze_bytes(wav_bytes(click_track(90, 5)), "x.wav")
        analyze_bytes(b"broken", "y.mp3")
        after = set(Path(tempfile.gettempdir()).glob("playline_*"))
        self.assertEqual(after - before, set())

    def test_title(self):
        self.assertEqual(title_from_filename("my_song_01.mp3"), "my song 01")
        self.assertEqual(title_from_filename("노을 산책.wav"), "노을 산책")


if __name__ == "__main__":
    unittest.main()
