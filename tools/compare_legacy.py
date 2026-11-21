# [AI 보조 도구: Claude Code (Claude Opus 5.5), 작업: '기존 분석 코드와 모듈화한 분석 결과 비교 스크립트']
"""기존 audio_analysis.py.py 와 playline.analysis 의 결과를 같은 음원으로 비교한다.

기존 스크립트는 수정하지 않고, 임시 폴더에 복사해 그림 창 없이(MPLBACKEND=Agg) 실행한 뒤
터미널 출력값을 읽는다. 원래 폴더의 analysis_result.png 는 덮어쓰지 않는다.

실행:  python tools/compare_legacy.py [음원 경로]   (기본값: Nostalgia.mp3)
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from playline.analysis import analyze_path  # noqa: E402


def run_legacy(audio: Path) -> dict:
    legacy = ROOT / "audio_analysis.py.py"
    with tempfile.TemporaryDirectory(prefix="playline_legacy_") as d:
        shutil.copy(legacy, Path(d) / "audio_analysis.py")
        shutil.copy(audio, Path(d) / "Nostalgia.mp3")  # 기존 코드가 이 이름을 읽는다
        env = dict(os.environ, MPLBACKEND="Agg", PYTHONIOENCODING="utf-8")
        out = subprocess.run([sys.executable, str(Path(d) / "audio_analysis.py")], cwd=d, env=env,
                             capture_output=True, text=True, encoding="utf-8", timeout=600)
    if out.returncode != 0:
        raise RuntimeError(out.stderr[-2000:])
    text = out.stdout
    return {
        "duration_sec": float(re.search(r"음원 길이: ([\d.]+)", text).group(1)),
        "bpm": float(re.search(r"추정 템포: ([\d.]+)", text).group(1)),
        "rms_mean": float(re.search(r"평균 RMS: ([\d.]+)", text).group(1)),
        "stdout": text.strip(),
    }


def main() -> int:
    audio = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "Nostalgia.mp3"
    if not audio.exists():
        print(f"음원을 찾을 수 없습니다: {audio}")
        return 1
    print(f"대상: {audio.name}")
    legacy = run_legacy(audio)
    new = analyze_path(audio)
    print("\n[기존 코드 출력]\n" + legacy["stdout"])
    print("\n[PLAYLINE 모듈]")
    print(f"상태: {new.status} {new.message}")
    print(f"음원 길이: {new.duration_sec:.1f}초")
    print(f"추정 템포: {new.bpm:.1f} BPM (절반/두 배 해석: {new.bpm_alternatives})")
    print(f"평균 RMS: {new.rms_mean:.4f}")
    print(f"SHA-256: {new.sha256}")
    same = (f"{new.duration_sec:.1f}" == f"{legacy['duration_sec']:.1f}"
            and f"{new.bpm:.1f}" == f"{legacy['bpm']:.1f}"
            and f"{new.rms_mean:.4f}" == f"{legacy['rms_mean']:.4f}")
    print("\n비교 결과(기존 출력 자릿수 기준):", "일치" if same else "불일치")
    return 0 if same else 2


if __name__ == "__main__":
    raise SystemExit(main())
