# [AI 보조 도구: Claude Code (Claude Opus 5.5), 작업: '공개 음악 검색 API로 곡 커버 주소 찾기']
"""라이브러리·데모 곡의 앨범 커버 주소를 Apple iTunes Search API에서 찾아 JSON에 기록한다.

    python -X utf8 tools/fetch_covers.py            # 커버가 없는 곡만
    python -X utf8 tools/fetch_covers.py --all      # 전부 다시 찾기

- 이미지 파일을 내려받아 저장소에 넣지 않고, Apple이 제공하는 커버 이미지 주소(mzstatic.com)만 기록한다.
- 곡명이 같다고 바로 쓰지 않는다. 아티스트가 있으면 아티스트도 일치해야 하고,
  아티스트를 모르는 라이브러리 곡은 실제 파일 길이와 3초 이내로 같은 곡만 고른다.
- 일치하는 곡을 못 찾으면 커버를 비워 두고(화면에서는 디스크 그림) 이유를 출력한다.
- 이 스크립트가 외부로 보내는 것은 곡명·아티스트 검색어뿐이다(음원·개인정보는 보내지 않음).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIBRARY = ROOT / "data" / "library.json"
DEMO = ROOT / "data" / "demo_tracks.json"
API = "https://itunes.apple.com/search"
SOURCE = "Apple iTunes Search API"
DURATION_TOL = 3.0


def norm(s: str | None) -> str:
    s = unicodedata.normalize("NFKC", s or "").lower()
    s = re.sub(r"\(.*?\)|\[.*?\]", " ", s)               # (feat. …), (Narr. …) 등 제거
    s = re.sub(r"feat\..*|ft\..*|with .*", " ", s)
    return re.sub(r"[^0-9a-z가-힣ぁ-んァ-ン一-龥]+", "", s)


def artist_tokens(s: str | None) -> set[str]:
    """'소연 (SOYEON)' → {'소연', 'soyeon'}, 'Tame Impala & JENNIE' → {'tameimpala', 'jennie'}"""
    s = unicodedata.normalize("NFKC", s or "").lower()
    parts = re.split(r"[()\[\]&,/·]|\bx\b|\band\b|\bfeat\.?", s)
    return {re.sub(r"[^0-9a-z가-힣]+", "", p) for p in parts if re.sub(r"[^0-9a-z가-힣]+", "", p)}


def search(term: str, country: str = "US", limit: int = 50) -> list[dict]:
    q = urllib.parse.urlencode({"term": term, "media": "music", "entity": "song", "limit": limit, "country": country})
    req = urllib.request.Request(f"{API}?{q}", headers={"User-Agent": "PLAYLINE-cover-lookup/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r).get("results", [])


def image_close(a: bytes | None, b: bytes | None, limit: float = 22.0) -> bool:
    """두 이미지를 24×24 흑백으로 줄여 평균 밝기 차이로 같은 그림인지 본다."""
    if not a or not b:
        return False
    try:
        import io as _io
        from PIL import Image
        def small(x):
            im = Image.open(_io.BytesIO(x)).convert("L")
            w, h = im.size
            side = min(w, h)
            im = im.crop(((w - side) // 2, (h - side) // 2, (w - side) // 2 + side, (h - side) // 2 + side))
            return list(im.resize((24, 24)).tobytes())
        pa, pb = small(a), small(b)
        return sum(abs(x - y) for x, y in zip(pa, pb)) / len(pa) <= limit
    except Exception:
        return False


def fetch(url: str) -> bytes | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "PLAYLINE-cover-lookup/1.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read()
    except Exception:
        return None


def title_keys(entry: dict) -> list[str]:
    return [k for k in (norm(entry.get("title")), norm(entry.get("title_alias"))) if k]


def pick(entry: dict, results: list[dict], duration: float | None, embedded: bytes | None = None
         ) -> tuple[dict | None, str]:
    wants = title_keys(entry)
    want_artist = artist_tokens(entry.get("artist")) | artist_tokens(entry.get("artist_alias"))
    cands = []
    for r in results:
        t = norm(r.get("trackName"))
        if not t or not any(t == w or t.startswith(w) or w.startswith(t) for w in wants):
            continue
        want_title = next(w for w in wants if t == w or t.startswith(w) or w.startswith(t))
        if "instrumental" in (r.get("trackName", "") + r.get("collectionName", "")).lower() and \
                "instrumental" not in (entry.get("title") or "").lower():
            continue
        got_artist = artist_tokens(r.get("artistName"))
        artist_ok = bool(want_artist & got_artist) or any(a in norm(r.get("artistName")) for a in want_artist if len(a) >= 3)
        secs = (r.get("trackTimeMillis") or 0) / 1000
        dur_ok = duration is not None and abs(secs - duration) <= DURATION_TOL
        if want_artist and not artist_ok:
            continue
        if not want_artist and not dur_ok:
            continue
        cands.append((0 if t == want_title else 1, abs(secs - duration) if duration else 0, r))
    if not cands:
        return None, "일치하는 곡 없음"
    cands.sort(key=lambda c: (c[0], "remix" in (c[2].get("collectionName") or "").lower(), c[1]))
    if want_artist:
        return cands[0][2], "아티스트 일치"
    # 아티스트를 모르면 곡명·길이만으로는 확정하지 않는다: 파일 속 커버와 같은 그림이어야 한다
    for _, _, r in cands:
        if image_close(embedded, fetch(r.get("artworkUrl100", ""))):
            return r, f"곡명 + 길이(±{DURATION_TOL:g}초) + 파일 속 커버 이미지 일치"
    names = ", ".join(sorted({r.get("artistName", "?") for _, _, r in cands}))
    return None, f"아티스트를 몰라 확정 못 함 (후보: {names}) — build_library.py --artist 로 아티스트를 알려 주세요"


def lookup(entry: dict, duration: float | None, embedded: bytes | None = None) -> tuple[dict | None, str]:
    terms = []
    for title in (entry.get("title_alias"), entry.get("title")):
        if not title:
            continue
        for artist in (entry.get("artist_alias"), entry.get("artist")):
            terms.append(f"{title} {artist or ''}".strip())
        for a in artist_tokens(entry.get("artist")) | artist_tokens(entry.get("artist_alias")):
            terms.append(f"{title} {a}")
        terms.append(title)
    last_why = "일치하는 곡 없음"
    seen = set()
    for term in terms:
        term = re.sub(r"\s*\((feat|narr)[^)]*\)", "", term or "", flags=re.I).strip()
        if not term or term in seen:
            continue
        seen.add(term)
        for country in ("US", "KR"):
            try:
                res = search(term, country, limit=200 if duration and not entry.get("artist") else 50)
            except Exception as e:  # 네트워크 오류는 다음 검색어로
                print(f"   검색 실패({country}): {e}")
                continue
            hit, why = pick(entry, res, duration, embedded)
            if hit:
                return hit, why
            if why != "일치하는 곡 없음":
                last_why = why
            time.sleep(0.4)
    return None, last_why


def apply(entry: dict, hit: dict, why: str, fill_artist: bool):
    art = hit.get("artworkUrl100", "").replace("100x100bb", "600x600bb")
    entry["cover_url"] = art
    entry["cover_source"] = SOURCE
    entry["cover_match"] = {"track": hit.get("trackName"), "artist": hit.get("artistName"),
                            "album": hit.get("collectionName"), "url": hit.get("trackViewUrl"), "rule": why,
                            "checked_on": date.today().isoformat()}
    if fill_artist and not entry.get("artist"):
        entry["artist"] = hit.get("artistName")
        entry["artist_source"] = f"{SOURCE} ({why})"


def run_file(path: Path, kind: str, redo: bool) -> tuple[int, int]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    found = total = 0
    for e in raw.get("tracks", []):
        total += 1
        if e.get("cover_url") and not redo:
            found += 1
            continue
        if redo and e.get("artist_source"):          # 예전에 자동으로 채운 아티스트는 다시 확인
            e.pop("artist", None)
            e.pop("artist_source", None)
        duration = e.get("duration_sec") if kind == "library" else None
        embedded = None
        if kind == "library" and e.get("filename"):
            f = ROOT / "library" / e["filename"]
            if f.is_file():
                sys.path.insert(0, str(ROOT))
                from playline.covers import extract_cover
                embedded = extract_cover(f.read_bytes())
        hit, why = lookup(e, duration, embedded)
        if hit:
            apply(e, hit, why, fill_artist=(kind == "library"))
            found += 1
            print(f"[O] {e['title']} → {hit['artistName']} · {hit.get('collectionName')} ({why})")
        else:
            for k in ("cover_url", "cover_source", "cover_match"):
                e.pop(k, None)
            print(f"[X] {e['title']} / {e.get('artist') or '아티스트 모름'} — {why} (디스크 그림으로 표시)")
    path.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return found, total


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--all", action="store_true", help="이미 찾은 곡도 다시 찾기")
    args = ap.parse_args()
    for path, kind in ((LIBRARY, "library"), (DEMO, "demo")):
        if path.exists():
            print(f"\n== {path.name}")
            f, t = run_file(path, kind, args.all)
            print(f"   커버 {f}/{t}곡")
    return 0


if __name__ == "__main__":
    sys.exit(main())
