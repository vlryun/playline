# [AI 보조 도구: Claude Code (Claude Opus 5.5), 작업: '흐름 체험 데모 목록 로드와 검증']
"""흐름 체험 데모 데이터.

data/demo_tracks.json 의 곡명·아티스트는 공개 차트에서 확인한 것이지만,
bpm·rms 는 앱 사용 흐름을 보여주기 위한 **가상값**이다. 실제 측정값으로 표시하지 않는다.
곡 목록을 바꾸고 싶으면 이 JSON 파일을 편집하거나 앱의 '데모 목록 편집'을 사용한다.
"""

from __future__ import annotations

import json
from pathlib import Path

DEMO_PATH = Path(__file__).resolve().parent.parent / "data" / "demo_tracks.json"


def load_demo(path: Path = DEMO_PATH) -> tuple[dict, list[dict]]:
    """(메타 정보, 트랙 목록)을 돌려준다. 트랙은 앱 내부 형식으로 변환한다."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    meta = {k: raw.get(k) for k in ("about", "checked_on", "sources")}
    tracks = []
    for i, t in enumerate(raw.get("tracks", []), start=1):
        tracks.append(demo_track(
            tid=str(t.get("id") or f"demo-{i:02d}"), title=str(t["title"]),
            artist=t.get("artist"), category=t.get("category"), chart=t.get("chart"),
            bpm=t.get("bpm"), rms=t.get("rms"), cover_url=t.get("cover_url"),
        ))
    return meta, tracks


def demo_track(*, tid: str, title: str, artist, category, chart, bpm, rms, cover_url=None) -> dict:
    from .library import safe_cover_url
    bpm = None if bpm in (None, "") else float(bpm)
    if bpm is not None and bpm <= 0:
        bpm = None
    return {
        "id": tid, "title": title.strip() or tid, "artist": (artist or None),
        "category": category or None, "chart": chart or None,
        "filename": None, "sha256": None, "size_bytes": None, "duration_sec": None,
        "bpm_raw": bpm, "bpm_factor": 1.0, "rms": float(rms),
        "status": "ok" if bpm is not None else "bpm_failed",
        "bpm_alternatives": [], "is_demo": True, "source": "demo", "analysis_scope": None, "cover_url": safe_cover_url(cover_url),
    }
