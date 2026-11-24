# [AI 보조 도구: Claude Code (Claude Opus 5.5),
# 작업: '배열 결과의 CSV·JSON 저장, JSON 불러오기 검증, 해시 기반 음원 재연결 구현']
"""저장·불러오기.

- JSON에는 음원 파일이 들어가지 않는다. 곡 식별 정보(파일명, SHA-256 해시, 크기),
  분석값, 순서, 설정, 저장한 버전만 담는다.
- 새 세션에서 JSON을 불러온 뒤 음원을 다시 올리면, 파일 이름이 아니라 SHA-256 해시가
  같은 경우에만 곡과 음원을 연결한다.
"""

from __future__ import annotations

import csv
import io
import json
import math
import re
from datetime import datetime, timezone

from .arrange import MODES

SCHEMA_VERSION = 1
APP_ID = "PLAYLINE"
MAX_TRACKS = 500
MAX_JSON_BYTES = 5 * 1024 * 1024
_HEX64 = re.compile(r"^[0-9a-f]{64}$")

AUDIO_NOT_INCLUDED = (
    "이 파일에는 음원이 포함되어 있지 않습니다. 새 세션에서 재생하려면 같은 음원 파일을 다시 올려야 하며, "
    "파일 내용(SHA-256 해시)이 같을 때만 연결됩니다."
)


def effective_bpm(t: dict) -> float | None:
    if t.get("bpm_raw") is None:
        return None
    return float(t["bpm_raw"]) * float(t.get("bpm_factor", 1.0))


def _fmt_duration(sec: float | None) -> str:
    if sec is None:
        return ""
    sec = int(round(sec))
    return f"{sec // 60}:{sec % 60:02d}"


def to_csv(order: list[str], tracks: dict[str, dict], scores: dict | None = None,
           data_kind: str = "measured") -> bytes:
    """순서·곡명·길이·BPM·RMS를 CSV로. 엑셀에서 한글이 깨지지 않도록 UTF-8 BOM을 붙인다."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["순서", "곡명", "아티스트", "파일명", "길이(초)", "길이", "BPM(추정)", "BPM 해석 배율",
                "평균 RMS", "흐름 점수(상대값)", "데이터 종류"])
    kind = "예시 데이터(가상값)" if data_kind == "demo" else "실제 분석값"
    for i, tid in enumerate(order, start=1):
        t = tracks[tid]
        bpm = effective_bpm(t)
        sc = scores.get(tid).score if scores and tid in scores else None
        w.writerow([
            i, t.get("title", ""), t.get("artist") or "", t.get("filename") or "",
            "" if t.get("duration_sec") is None else f"{t['duration_sec']:.1f}",
            _fmt_duration(t.get("duration_sec")),
            "" if bpm is None else f"{bpm:.1f}",
            t.get("bpm_factor", 1.0),
            "" if t.get("rms") is None else f"{t['rms']:.4f}",
            "" if sc is None else f"{sc:.3f}",
            kind,
        ])
    return ("﻿" + buf.getvalue()).encode("utf-8")


_TRACK_KEYS = ("id", "title", "artist", "filename", "sha256", "size_bytes", "duration_sec",
               "bpm_raw", "bpm_factor", "rms", "status", "category", "bpm_alternatives", "source", "cover_url")


def to_json(*, tracks: dict[str, dict], original: list[str], suggested: list[str] | None,
            current: list[str], settings: dict, versions: list[dict], data_kind: str,
            excluded: list[dict] | None = None) -> bytes:
    payload = {
        "app": APP_ID,
        "schema_version": SCHEMA_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "note": AUDIO_NOT_INCLUDED,
        "data_kind": data_kind,
        "tracks": [{k: tracks[tid].get(k) for k in _TRACK_KEYS} for tid in original],
        "orders": {"original": original, "suggested": suggested, "current": current},
        "settings": settings,
        "versions": versions,
        "excluded": excluded or [],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def _num(v, *, allow_none=False, min_value=None) -> bool:
    if v is None:
        return allow_none
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        return False
    return min_value is None or v >= min_value


def _is_perm(seq, ids: set[str]) -> bool:
    return isinstance(seq, list) and all(isinstance(x, str) for x in seq) \
        and len(seq) == len(ids) and set(seq) == ids


def validate_settings(s, ids: set[str]) -> list[str]:
    errs = []
    if not isinstance(s, dict):
        return ["settings 항목이 올바르지 않습니다."]
    if s.get("mode") not in MODES:
        errs.append("흐름 모드(settings.mode)가 올바르지 않습니다.")
    if not _num(s.get("bpm_weight")) or not 0 <= s["bpm_weight"] <= 1:
        errs.append("BPM 반영 비중(settings.bpm_weight)은 0~1 사이 숫자여야 합니다.")
    if not _num(s.get("smooth")) or not 0 <= s["smooth"] <= 1:
        errs.append("인접 변화 가중치(settings.smooth)는 0~1 사이 숫자여야 합니다.")
    for key in ("pin_first", "pin_last"):
        v = s.get(key)
        if v is not None and v not in ids:
            errs.append(f"고정 곡({key})이 곡 목록에 없습니다.")
    if s.get("pin_first") is not None and s.get("pin_first") == s.get("pin_last"):
        errs.append("같은 곡이 첫 곡과 마지막 곡으로 동시에 고정되어 있습니다.")
    return errs


def parse_project(raw: bytes) -> tuple[dict | None, list[str]]:
    """JSON 프로젝트 파일을 읽고 검증한다. (프로젝트, 오류 목록)을 돌려준다."""
    if len(raw) > MAX_JSON_BYTES:
        return None, ["JSON 파일이 너무 큽니다(5MB 초과)."]
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except UnicodeDecodeError:
        return None, ["UTF-8 텍스트 파일이 아닙니다."]
    except json.JSONDecodeError as exc:
        return None, [f"JSON 형식이 올바르지 않습니다 ({exc.lineno}번째 줄 근처)."]

    if not isinstance(data, dict) or data.get("app") != APP_ID:
        return None, ["PLAYLINE에서 저장한 JSON 파일이 아닙니다."]
    if data.get("schema_version") != SCHEMA_VERSION:
        return None, [f"지원하지 않는 파일 버전입니다(schema_version={data.get('schema_version')!r})."]
    if data.get("data_kind") not in ("measured", "demo"):
        return None, ["data_kind 값이 올바르지 않습니다."]

    errs: list[str] = []
    tracks = data.get("tracks")
    if not isinstance(tracks, list) or not tracks:
        return None, ["곡 목록(tracks)이 비어 있거나 올바르지 않습니다."]
    if len(tracks) > MAX_TRACKS:
        return None, [f"곡이 {MAX_TRACKS}곡을 넘습니다."]

    clean: dict[str, dict] = {}
    for i, t in enumerate(tracks, start=1):
        where = f"{i}번째 곡"
        if not isinstance(t, dict):
            errs.append(f"{where}: 형식이 올바르지 않습니다.")
            continue
        tid = t.get("id")
        if not isinstance(tid, str) or not tid:
            errs.append(f"{where}: id가 없습니다.")
            continue
        if tid in clean:
            errs.append(f"{where}: id가 중복됩니다({tid}).")
            continue
        if not isinstance(t.get("title"), str) or not t["title"].strip():
            errs.append(f"{where}: 곡명이 없습니다.")
        if not _num(t.get("rms"), min_value=0):
            errs.append(f"{where}: 평균 RMS 값이 올바르지 않습니다.")
        if not _num(t.get("bpm_raw"), allow_none=True) or (t.get("bpm_raw") is not None and t["bpm_raw"] <= 0):
            errs.append(f"{where}: BPM 값이 올바르지 않습니다.")
        if t.get("bpm_factor", 1.0) not in (0.5, 1, 1.0, 2, 2.0):
            errs.append(f"{where}: BPM 해석 배율은 0.5, 1, 2 중 하나여야 합니다.")
        if not _num(t.get("duration_sec"), allow_none=True, min_value=0):
            errs.append(f"{where}: 길이 값이 올바르지 않습니다.")
        sha = t.get("sha256")
        if data["data_kind"] == "measured":
            if not isinstance(sha, str) or not _HEX64.match(sha):
                errs.append(f"{where}: 실제 분석 데이터에는 SHA-256 해시가 필요합니다.")
        elif sha is not None and (not isinstance(sha, str) or not _HEX64.match(sha)):
            errs.append(f"{where}: SHA-256 해시 형식이 올바르지 않습니다.")
        clean[tid] = {k: t.get(k) for k in _TRACK_KEYS}
        clean[tid]["bpm_factor"] = float(t.get("bpm_factor", 1.0) or 1.0)
        if clean[tid].get("bpm_alternatives") is None:
            clean[tid]["bpm_alternatives"] = []
        if clean[tid].get("source") != "library":
            clean[tid]["source"] = None
        from .library import safe_cover_url
        clean[tid]["cover_url"] = safe_cover_url(clean[tid].get("cover_url"))

    if errs:
        return None, errs

    ids = set(clean)
    orders = data.get("orders")
    if not isinstance(orders, dict):
        return None, ["순서(orders) 정보가 없습니다."]
    for key in ("original", "current"):
        if not _is_perm(orders.get(key), ids):
            errs.append(f"{key} 순서에 모든 곡이 정확히 한 번씩 들어 있지 않습니다.")
    if orders.get("suggested") is not None and not _is_perm(orders["suggested"], ids):
        errs.append("suggested 순서에 모든 곡이 정확히 한 번씩 들어 있지 않습니다.")
    errs += validate_settings(data.get("settings"), ids)

    versions_in = data.get("versions", [])
    versions = []
    if not isinstance(versions_in, list):
        errs.append("versions 항목이 올바르지 않습니다.")
    else:
        for i, v in enumerate(versions_in, start=1):
            if not isinstance(v, dict) or not isinstance(v.get("name"), str) or not v["name"].strip():
                errs.append(f"{i}번째 버전: 이름이 없습니다.")
            elif not _is_perm(v.get("order"), ids):
                errs.append(f"{i}번째 버전 '{v['name']}': 곡 목록과 순서가 맞지 않습니다.")
            elif validate_settings(v.get("settings"), ids):
                errs.append(f"{i}번째 버전 '{v['name']}': 설정 값이 올바르지 않습니다.")
            else:
                versions.append({"name": v["name"].strip(), "created_at": str(v.get("created_at", "")),
                                 "order": list(v["order"]), "settings": dict(v["settings"])})
    if errs:
        return None, errs

    for t in clean.values():
        t["status"] = t.get("status") if t.get("status") in ("ok", "bpm_failed") else (
            "ok" if t.get("bpm_raw") is not None else "bpm_failed")

    project = {
        "data_kind": data["data_kind"],
        "tracks": clean,
        "original": list(orders["original"]),
        "suggested": list(orders["suggested"]) if orders.get("suggested") else None,
        "current": list(orders["current"]),
        "settings": dict(data["settings"]),
        "versions": versions,
        "exported_at": data.get("exported_at"),
    }
    return project, []


def match_audio(tracks: dict[str, dict], uploads: dict[str, dict]) -> dict:
    """해시로 곡과 업로드 음원을 연결한다.

    uploads: sha256 -> {'filename', ...}
    반환: {'linked': {track_id: sha}, 'missing': [track_id], 'extra': [sha],
           'renamed': [(track_id, new_filename)]}
    """
    linked, missing, renamed = {}, [], []
    used = set()
    for tid, t in tracks.items():
        sha = t.get("sha256")
        if sha and sha in uploads:
            linked[tid] = sha
            used.add(sha)
            if uploads[sha].get("filename") != t.get("filename"):
                renamed.append((tid, uploads[sha].get("filename")))
        else:
            missing.append(tid)
    extra = [sha for sha in uploads if sha not in used]
    return {"linked": linked, "missing": missing, "extra": extra, "renamed": renamed}
