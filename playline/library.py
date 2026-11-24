# [AI 보조 도구: Claude Code (Claude Opus 5.5), 작업: '음원 라이브러리(미리 분석한 곡 목록) 로드']
"""음원 라이브러리.

data/library.json 에는 미리 librosa로 분석해 둔 곡의 **실제 분석값**(BPM·RMS·길이)과
파일 식별 정보(SHA-256)가 들어 있다. 사용자는 파일을 올리지 않고 이 목록에서 곡을 골라
바로 흐름 배열을 할 수 있다.

음원 파일 자체는 library/ 폴더에 둔다. 저작권이 있는 음원은 공개 저장소와 배포 사이트에
올리지 않으므로(.gitignore), 그런 곡은 배포판에서 분석값만 보이고 재생은 되지 않는다.
library/ 에 같은 내용(SHA-256)의 파일이 있는 서버(예: 로컬 실행)에서는 재생된다.

곡 추가: python -X utf8 tools/build_library.py <음원 파일 또는 폴더> ...
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIBRARY_PATH = ROOT / "data" / "library.json"
AUDIO_DIR = ROOT / "library"
# 커버 썸네일: data/covers 는 공개 저장소에 포함(재배포 가능한 이미지만), library/covers 는 로컬 전용
COVER_DIRS = (ROOT / "data" / "covers", AUDIO_DIR / "covers")
MIME = {".mp3": "audio/mpeg", ".wav": "audio/wav"}


def safe_cover_url(url) -> str | None:
    """Apple 이미지 서버(https://*.mzstatic.com)의 커버 주소만 쓴다."""
    import re
    if isinstance(url, str) and re.match(r"^https://is\d+-ssl\.mzstatic\.com/[\w./%-]+$", url):
        return url
    return None


def load_library(path: Path = LIBRARY_PATH) -> list[dict]:
    """라이브러리 곡 목록(원본 JSON 항목)을 돌려준다. 파일이 없으면 빈 목록."""
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [t for t in raw.get("tracks", []) if t.get("sha256") and t.get("rms") is not None]


def save_library(tracks: list[dict], path: Path = LIBRARY_PATH) -> None:
    data = {
        "app": "PLAYLINE",
        "about": "미리 librosa로 분석한 곡의 실제 분석값. 음원 파일은 library/ 폴더에 따로 두며, "
                 "저작권 음원은 공개 저장소에 포함하지 않는다.",
        "tracks": sorted(tracks, key=lambda t: (t.get("title") or "").lower()),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def to_track(entry: dict) -> dict:
    """라이브러리 항목을 앱 내부 트랙 형식으로 바꾼다(업로드 분석 결과와 같은 형식)."""
    sha = entry["sha256"]
    bpm = entry.get("bpm")
    return {
        "id": sha[:12], "title": entry.get("title") or entry.get("filename") or sha[:12],
        "artist": entry.get("artist") or None, "filename": entry.get("filename"), "sha256": sha,
        "size_bytes": entry.get("size_bytes"), "duration_sec": entry.get("duration_sec"),
        "bpm_raw": None if bpm is None else float(bpm), "bpm_factor": 1.0, "rms": float(entry["rms"]),
        "status": "ok" if bpm is not None else "bpm_failed", "category": entry.get("genre") or None,
        "bpm_alternatives": [] if bpm is None else [round(bpm / 2, 1), round(bpm * 2, 1)],
        "message": None, "source": "library", "analysis_scope": entry.get("analysis_scope") or "full", "cover_url": safe_cover_url(entry.get("cover_url")),
    }


def audio_files(entries: list[dict], audio_dir: Path = AUDIO_DIR) -> dict[str, dict]:
    """서버에 실제 음원 파일이 있는 라이브러리 곡: sha256 -> {'filename','path','mime','size','data': None}.

    파일 내용을 매번 해시하지 않도록 파일 이름과 크기로 확인하고, 크기가 다르면 연결하지 않는다.
    """
    out: dict[str, dict] = {}
    for e in entries:
        fn = e.get("filename")
        if not fn:
            continue
        p = audio_dir / fn
        if p.is_file() and (e.get("size_bytes") in (None, p.stat().st_size)):
            out[e["sha256"]] = {"filename": fn, "path": str(p), "data": None,
                                "mime": MIME.get(p.suffix.lower(), "audio/mpeg"), "size": p.stat().st_size}
    return out


def cover_path(sha: str, dirs=COVER_DIRS) -> Path | None:
    for d in dirs:
        p = Path(d) / f"{sha[:12]}.jpg"
        if p.is_file():
            return p
    return None


def cover_uris(entries: list[dict], dirs=COVER_DIRS) -> dict[str, str]:
    """sha256 -> 커버 썸네일 data URI (파일이 있는 곡만)."""
    from .covers import data_uri
    out = {}
    for e in entries:
        p = cover_path(e["sha256"], dirs)
        if p is not None:
            out[e["sha256"]] = data_uri(p.read_bytes())
    return out


def search(entries: list[dict], query: str) -> list[dict]:
    q = (query or "").strip().lower()
    if not q:
        return entries
    return [e for e in entries
            if q in " ".join(str(e.get(k) or "") for k in ("title", "artist", "genre", "filename")).lower()]
