# [AI 보조 도구: Claude Code (Claude Opus 5.5),
# 작업: 'BPM·RMS 정규화 기반 흐름 점수와 목표 곡선 배치 알고리즘 구현']
"""흐름 점수와 자동 배열.

알고리즘 (같은 입력이면 항상 같은 결과, 무작위 요소 없음)
1. 곡 목록 안에서 BPM과 평균 RMS를 각각 최소-최대 정규화한다(0~1).
   - 값이 모두 같으면 0.5로 둔다.
   - BPM을 추정하지 못한 곡은 RMS만으로 점수를 만든다.
2. 가중 평균으로 '흐름 점수'를 만든다. 이 점수는 같은 목록 안에서만 의미가 있는
   상대적 배열 지표이며, 음악 감정의 객관적 점수가 아니다.
3. 모드에 맞는 목표 곡선을 만든다. 곡선은 이 목록의 최저~최고 흐름 점수 범위에 맞춘다.
4. 고정 곡을 제외한 곡을 점수 순으로, 고정 위치를 제외한 자리를 목표값 순으로 정렬해
   차례로 짝짓는다. 1차원에서 이 방식은 목표와의 절대 오차 합을 최소로 만든다.
5. (선택) 인접 곡 사이 점수 변화가 큰 경우를 줄이기 위해, 두 곡의 자리를 바꿔
   '목표 오차 + λ × 인접 변화'가 줄어들면 교환하는 과정을 더 이상 개선이 없을 때까지 반복한다.

정규화 기준(최소·최대)은 곡 목록 전체에서 한 번만 계산하므로 원본·제안·수정 순서에
똑같이 적용된다.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

MODES = {
    "rise": {
        "label": "점차 고조",
        "desc": "차분한 곡에서 시작해 점점 빠르고 큰 소리의 곡으로 이어집니다.",
    },
    "fall": {
        "label": "점차 차분",
        "desc": "빠르고 큰 소리의 곡에서 시작해 점점 차분한 곡으로 마무리합니다.",
    },
    "arc": {
        "label": "고조 후 차분",
        "desc": "차분하게 시작해 중반에 가장 고조되고, 끝에서 다시 차분해집니다.",
    },
}

ARC_PEAK = 0.6  # 고조 후 차분 모드에서 가장 높은 지점의 상대 위치
EPS = 1e-12
SMOOTH_MAX_TRACKS = 120  # 이보다 많으면 교환 개선 단계를 생략 (속도)


def normalize(values: list[float | None]) -> list[float | None]:
    """최소-최대 정규화. None은 그대로 두고, 값이 모두 같으면 0.5."""
    valid = [v for v in values if v is not None and np.isfinite(v)]
    if not valid:
        return [None for _ in values]
    lo, hi = min(valid), max(valid)
    out: list[float | None] = []
    for v in values:
        if v is None or not np.isfinite(v):
            out.append(None)
        elif hi - lo < EPS:
            out.append(0.5)
        else:
            out.append((v - lo) / (hi - lo))
    return out


@dataclass
class ScoreInfo:
    score: float
    n_bpm: float | None
    n_rms: float
    basis: str  # "BPM+RMS" | "RMS만"


def compute_scores(tracks: list[dict], bpm_weight: float) -> dict[str, ScoreInfo]:
    """tracks: [{'id','bpm','rms'}]. bpm_weight: 0~1 (RMS 비중 = 1 - bpm_weight)."""
    w_b = float(min(max(bpm_weight, 0.0), 1.0))
    w_r = 1.0 - w_b
    n_bpm = normalize([t.get("bpm") for t in tracks])
    n_rms = normalize([t.get("rms") for t in tracks])
    out: dict[str, ScoreInfo] = {}
    for t, b, r in zip(tracks, n_bpm, n_rms):
        if r is None:
            raise ValueError(f"RMS 값이 없는 곡은 배열할 수 없습니다: {t.get('id')}")
        if b is None:
            score = r
            basis = "RMS만"
        else:
            score = w_b * b + w_r * r
            basis = "BPM+RMS"
        out[t["id"]] = ScoreInfo(score=float(score), n_bpm=b, n_rms=float(r), basis=basis)
    return out


def target_shape(mode: str, n: int) -> np.ndarray:
    """0~1 범위의 목표 곡선 모양."""
    if mode not in MODES:
        raise ValueError(f"알 수 없는 흐름 모드: {mode}")
    if n <= 0:
        return np.zeros(0)
    if n == 1:
        return np.array([0.5])
    x = np.linspace(0.0, 1.0, n)
    if mode == "rise":
        return x
    if mode == "fall":
        return 1.0 - x
    p = ARC_PEAK
    return np.where(x <= p, x / p, (1.0 - x) / (1.0 - p))


def target_curve(mode: str, n: int, lo: float, hi: float) -> np.ndarray:
    """목표 곡선을 이 목록의 흐름 점수 범위 [lo, hi]에 맞춘다."""
    shape = target_shape(mode, n)
    if hi - lo < EPS:
        return np.full(n, lo)
    if n == 1:
        return np.array([(lo + hi) / 2])
    return lo + shape * (hi - lo)


def score_range(scores: dict[str, ScoreInfo]) -> tuple[float, float]:
    vals = [s.score for s in scores.values()]
    return (min(vals), max(vals)) if vals else (0.0, 0.0)


def _objective(seq: np.ndarray, target: np.ndarray, smooth: float) -> float:
    n = len(seq)
    err = float(np.abs(seq - target).sum()) / n
    if n < 2 or smooth <= 0:
        return err
    return err + smooth * float(np.abs(np.diff(seq)).sum()) / (n - 1)


@dataclass
class ArrangeResult:
    order: list[str] | None
    error: str | None = None
    notes: list[str] | None = None


def arrange(order: list[str], scores: dict[str, ScoreInfo], mode: str,
            pin_first: str | None = None, pin_last: str | None = None,
            smooth: float = 0.2) -> ArrangeResult:
    """흐름 모드에 맞춘 순서를 제안한다.

    order    : 원본 순서(동점일 때 원본 순서가 앞선 곡을 먼저 둔다)
    pin_first: 첫 곡으로 고정할 곡 id
    pin_last : 마지막 곡으로 고정할 곡 id
    smooth   : 인접 변화 보조 기준 가중치 λ (0이면 사용 안 함)
    """
    n = len(order)
    notes: list[str] = []
    if n == 0:
        return ArrangeResult(order=[], notes=["배열할 곡이 없습니다."])
    if len(set(order)) != n:
        return ArrangeResult(order=None, error="곡 목록에 중복된 항목이 있습니다.")
    for pid in (pin_first, pin_last):
        if pid is not None and pid not in scores:
            return ArrangeResult(order=None, error="고정한 곡이 현재 목록에 없습니다. 고정을 다시 선택해 주세요.")
    if n == 1:
        return ArrangeResult(order=list(order), notes=["곡이 한 곡뿐이라 순서를 바꿀 수 없습니다."])
    if pin_first is not None and pin_first == pin_last:
        return ArrangeResult(order=None, error="같은 곡을 첫 곡과 마지막 곡으로 동시에 고정할 수 없습니다.")

    lo, hi = score_range(scores)
    target = target_curve(mode, n, lo, hi)
    rank = {tid: i for i, tid in enumerate(order)}

    slots: list[str | None] = [None] * n
    if pin_first is not None:
        slots[0] = pin_first
    if pin_last is not None:
        slots[n - 1] = pin_last

    free_pos = [i for i in range(n) if slots[i] is None]
    pinned = {p for p in (pin_first, pin_last) if p is not None}
    free_ids = [t for t in order if t not in pinned]

    ids_sorted = sorted(free_ids, key=lambda t: (scores[t].score, rank[t]))
    pos_sorted = sorted(free_pos, key=lambda i: (target[i], i))
    for tid, pos in zip(ids_sorted, pos_sorted):
        slots[pos] = tid

    result = [s for s in slots if s is not None]

    if smooth > 0 and len(free_pos) >= 2 and n <= SMOOTH_MAX_TRACKS:
        seq = np.array([scores[t].score for t in result])
        best = _objective(seq, target, smooth)
        improved = True
        guard = 0
        while improved and guard < 200:
            improved = False
            guard += 1
            for a_i in range(len(free_pos)):
                for b_i in range(a_i + 1, len(free_pos)):
                    a, b = free_pos[a_i], free_pos[b_i]
                    seq[a], seq[b] = seq[b], seq[a]
                    val = _objective(seq, target, smooth)
                    if val < best - 1e-12:
                        best = val
                        result[a], result[b] = result[b], result[a]
                        improved = True
                    else:
                        seq[a], seq[b] = seq[b], seq[a]
    elif smooth > 0 and n > SMOOTH_MAX_TRACKS:
        notes.append(f"곡이 {SMOOTH_MAX_TRACKS}곡을 넘어 인접 변화 보조 기준은 적용하지 않았습니다.")

    if hi - lo < EPS:
        notes.append("모든 곡의 흐름 점수가 같아 원본 순서를 유지했습니다.")

    assert sorted(result) == sorted(order), "모든 곡이 정확히 한 번씩 포함되어야 합니다"
    return ArrangeResult(order=result, notes=notes)


@dataclass
class OrderMetrics:
    mae: float            # 목표 곡선과의 평균 절대 오차
    mean_jump: float      # 인접 곡 사이 흐름 점수 변화의 평균
    max_jump: float       # 인접 곡 사이 흐름 점수 변화의 최댓값


def evaluate(order: list[str], scores: dict[str, ScoreInfo], mode: str) -> OrderMetrics:
    n = len(order)
    if n == 0:
        return OrderMetrics(0.0, 0.0, 0.0)
    lo, hi = score_range(scores)
    seq = np.array([scores[t].score for t in order])
    target = target_curve(mode, n, lo, hi)
    diffs = np.abs(np.diff(seq)) if n > 1 else np.zeros(1)
    return OrderMetrics(
        mae=float(np.abs(seq - target).mean()),
        mean_jump=float(diffs.mean()),
        max_jump=float(diffs.max()),
    )


def move(order: list[str], index: int, delta: int, locked: set[int]) -> list[str]:
    """index 위치의 곡을 delta(±1)만큼 옮긴다. 잠긴 자리는 움직이지 않는다."""
    j = index + delta
    if not (0 <= index < len(order)) or not (0 <= j < len(order)):
        return order
    if index in locked or j in locked:
        return order
    new = list(order)
    new[index], new[j] = new[j], new[index]
    return new


def apply_pins(order: list[str], pin_first: str | None, pin_last: str | None) -> list[str]:
    """수동 편집 순서에 고정 설정을 반영한다(고정 곡을 맨 앞/맨 뒤로)."""
    rest = [t for t in order if t not in (pin_first, pin_last)]
    out = ([pin_first] if pin_first else []) + rest + ([pin_last] if pin_last and pin_last != pin_first else [])
    return out
