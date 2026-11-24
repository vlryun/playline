# [AI 보조 도구: Claude Code (Claude Opus 5.5), 작업: '음원을 분석해 라이브러리에 추가하는 도구']
"""음원 파일을 분석해 PLAYLINE 라이브러리(data/library.json)에 추가한다.

사용 예 (PowerShell):
    python -X utf8 tools/build_library.py "C:\\Users\\me\\Music\\song.mp3"
    python -X utf8 tools/build_library.py "C:\\Users\\me\\Music" --title "song.mp3=곡 제목" --artist "song.mp3=아티스트"

- 음원은 library/ 폴더로 복사한다(재생용). 이 폴더의 음원은 .gitignore 로 공개 저장소에서 빠진다.
- 분석값은 앱의 업로드 분석과 같은 함수(playline.analysis.analyze_path)로 계산한다.
- 같은 내용(SHA-256)의 곡은 한 번만 들어가며, 다시 실행하면 값을 갱신한다.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playline import analysis  # noqa: E402
from playline.library import AUDIO_DIR, load_library, save_library  # noqa: E402

# 다운로드 사이트가 파일 이름 끝에 붙이는 꼬리표는 곡명에서 뺀다
_TAG = re.compile(r"[\s_\-]*(klickaud|y2mate|ytmp3|320kbps|128kbps|official audio|audio)$", re.I)


def clean_title(filename: str) -> str:
    t = analysis.title_from_filename(filename)
    prev = None
    while prev != t:
        prev, t = t, _TAG.sub("", t).strip()
    t = t or analysis.title_from_filename(filename)
    return t[:1].upper() + t[1:]


def parse_map(items: list[str]) -> dict[str, str]:
    out = {}
    for it in items or []:
        if "=" in it:
            k, v = it.split("=", 1)
            out[k.strip().lower()] = v.strip()
    return out


def collect(paths: list[str]) -> list[Path]:
    files: list[Path] = []
    for p in map(Path, paths):
        if p.is_dir():
            files += sorted(x for x in p.iterdir() if x.suffix.lower() in (".mp3", ".wav"))
        elif p.is_file():
            files.append(p)
        else:
            print(f"[건너뜀] 찾을 수 없음: {p}")
    return files


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+", help="음원 파일 또는 폴더")
    ap.add_argument("--title", action="append", help='"파일이름=곡 제목" (여러 번 가능)')
    ap.add_argument("--artist", action="append", help='"파일이름=아티스트" (여러 번 가능)')
    ap.add_argument("--no-copy", action="store_true", help="library/ 폴더로 음원을 복사하지 않음")
    args = ap.parse_args()

    titles, artists = parse_map(args.title), parse_map(args.artist)
    entries = {e["sha256"]: e for e in load_library()}
    AUDIO_DIR.mkdir(exist_ok=True)

    added = 0
    for f in collect(args.paths):
        print(f"분석 중: {f.name}", flush=True)
        res = analysis.analyze_path(f)
        if not res.usable:
            print(f"  [제외] {res.message}")
            continue
        old = entries.get(res.sha256, {})
        key = f.name.lower()
        entry = {
            "title": titles.get(key) or old.get("title") or clean_title(f.name),
            "artist": artists.get(key) or old.get("artist"),
            "genre": old.get("genre"),
            "filename": f.name,
            "sha256": res.sha256,
            "size_bytes": res.size_bytes,
            "duration_sec": round(res.duration_sec, 2) if res.duration_sec else None,
            "bpm": round(res.bpm, 2) if res.bpm is not None else None,
            "rms": round(res.rms_mean, 6),
            "status": res.status,
            "analyzed_on": date.today().isoformat(),
            "analyzer": f"librosa beat_track + rms (sr={analysis.SAMPLE_RATE})",
        }
        entries[res.sha256] = entry
        if not args.no_copy:
            dst = AUDIO_DIR / f.name
            if f.resolve() != dst.resolve():
                shutil.copy2(f, dst)
        bpm = "—" if entry["bpm"] is None else f"{entry['bpm']:.1f}"
        print(f"  → {entry['title']} · {entry['duration_sec']}s · BPM {bpm} · RMS {entry['rms']:.4f}")
        added += 1

    save_library(list(entries.values()))
    print(f"\n{added}곡 반영 · 라이브러리 총 {len(entries)}곡 → data/library.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
