# [AI 보조 도구: Claude Code (Claude Opus 5.5), 작업: '업로드 예외 상황 확인용 합성 음원 생성']
"""업로드 예외 상황을 확인하기 위한 테스트 파일을 만든다.

만들어지는 파일은 모두 **합성 신호**(일정한 타격음, 무음 등)이며 실제 음악이 아니다.
실제 음악으로 검증한 것처럼 쓰지 말 것.

실행:  python tools/make_test_audio.py [출력 폴더]   (기본값: test_audio)
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

SR = 22050


def beats(bpm, seconds, amp, seed):
    rng = np.random.default_rng(seed)
    y = np.zeros(int(seconds * SR), dtype=np.float32)
    period, L = int(round(60 / bpm * SR)), 2000
    env = np.exp(-np.arange(L) / 300)
    for s in range(0, len(y) - L, period):
        y[s:s + L] += (amp * env * rng.standard_normal(L)).astype(np.float32)
    return np.clip(y, -1, 1)


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "test_audio")
    out.mkdir(parents=True, exist_ok=True)
    sf.write(out / "합성 느린 비트 80.wav", beats(80, 20, 0.15, 1), SR)
    sf.write(out / "synthetic fast 150.wav", beats(150, 20, 0.6, 2), SR)
    sf.write(out / "합성 중간 비트 110.wav", beats(110, 20, 0.35, 3), SR)
    long_name = "아주 긴 제목의 합성 테스트 트랙 – 이름이 길어도 버튼과 겹치지 않는지 확인하기 위한 파일 120.wav"
    sf.write(out / long_name, beats(120, 15, 0.4, 4), SR)
    sf.write(out / "무음 테스트.wav", np.zeros(SR * 5, dtype=np.float32), SR)
    (out / "깨진 파일.mp3").write_bytes(b"not really an mp3 " * 500)
    # 같은 내용·다른 이름 (중복 파일)
    shutil.copy(out / "합성 중간 비트 110.wav", out / "중복 복사본.wav")
    # 같은 이름·다른 내용 (하위 폴더)
    sub = out / "same_name"
    sub.mkdir(exist_ok=True)
    sf.write(sub / "합성 느린 비트 80.wav", beats(95, 12, 0.25, 5), SR)
    print(f"테스트 파일을 만들었습니다: {out.resolve()}")


if __name__ == "__main__":
    main()
