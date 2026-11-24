# [AI 보조 도구: Claude Code (Claude Opus 5.5), 작업: "'왜 여기에?' 배치 근거 문장 만들기"]
"""'왜 여기에?' — 곡이 지금 자리에 놓인 근거를 실제 계산값으로 보여 준다.

정렬(arrange.arrange)은
  1) 고정한 첫·마지막 곡을 먼저 그 자리에 두고,
  2) 나머지 곡을 흐름 점수 순으로, 남은 자리를 목표값 순으로 정렬해 짝짓고,
  3) '곡 사이 부드럽게 잇기'(λ) 가 0보다 크면 이웃 곡 점수 차이도 함께 줄이도록 두 곡씩 자리를 바꿔 본다.
그래서 한 곡의 자리는 그 곡 하나만 보고 정해지지 않는다. 이 모듈은 '이 위치의 목표값과 곡의 점수 비교'만
보여 주고, 이 곡이 최적이라 뽑혔다고 말하지 않는다. 외부 AI 없이 계산값과 문장 틀로만 만든다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .arrange import ScoreInfo, score_range, target_curve, target_shape

EDGE = 0.05      # 목표 곡선 기울기를 '유지'로 볼 범위 (0~1 모양 기준)


@dataclass
class Placement:
    stale: bool = False
    lines: list[str] = field(default_factory=list)      # 위에서부터 보여 줄 문장
    note: str = ""                                      # 비교 정보라는 안내
    pos: int = 0
    n: int = 0
    target: float | None = None
    score: float | None = None
    diff: float | None = None
    formula: str = ""


_BATCHIM = set("013678")   # 영·일·삼·육·칠·팔: 받침이 있는 숫자


def iyo(num: str) -> str:
    return "이에요" if num[-1:] in _BATCHIM else "예요"


def igo(num: str) -> str:
    return "이고" if num[-1:] in _BATCHIM else "고"


def section_text(shape, i: int) -> str:
    """목표 곡선의 주변 값으로 구간을 간단히 말한다 (감정·음악적 의미는 말하지 않음)."""
    n = len(shape)
    if n <= 1:
        return "곡이 한 곡뿐이라 구간을 나누지 않아요."
    if i == 0:
        nxt = shape[1] - shape[0]
        trend = "이후 목표가 올라가요" if nxt > EDGE else ("이후 목표가 내려가요" if nxt < -EDGE else "이후 목표가 비슷하게 이어져요")
        return f"플레이리스트를 시작하는 자리예요. {trend}."
    if i == n - 1:
        prv = shape[-1] - shape[-2]
        trend = "목표가 올라가며 끝나요" if prv > EDGE else ("목표가 내려가며 끝나요" if prv < -EDGE else "목표가 비슷하게 끝나요")
        return f"플레이리스트를 마무리하는 자리예요. {trend}."
    a, b, c = shape[i - 1], shape[i], shape[i + 1]
    if b - a > EDGE / 2 and b - c > EDGE / 2:
        return "목표 흐름이 가장 높아지는 지점 근처예요."
    if a - b > EDGE / 2 and c - b > EDGE / 2:
        return "목표 흐름이 가장 낮아지는 지점 근처예요."
    d = c - a
    if d > EDGE:
        return "목표 흐름이 올라가는 구간이에요."
    if d < -EDGE:
        return "목표 흐름이 내려가는 구간이에요."
    return "목표 흐름이 비슷하게 유지되는 구간이에요."


def formula_text(info: ScoreInfo, bpm_weight: float, bpm, rms) -> str:
    """흐름 점수가 빠르기·소리 크기로 어떻게 계산됐는지 (같은 목록 안에서 0~1로 맞춘 값 사용)."""
    if info.n_bpm is None:
        return (f"이 곡은 빠르기를 재지 못해 소리 크기만 썼어요: 소리 크기 {rms:.4f} → 목록 안 위치 "
                f"{info.n_rms:.2f} = 흐름 점수 {info.score:.3f}.")
    wb = bpm_weight
    return (f"흐름 점수 {info.score:.3f} = 빠르기 {bpm:.1f} BPM(목록 안 위치 {info.n_bpm:.2f}) × {wb:.0%} "
            f"+ 소리 크기 {rms:.4f}(목록 안 위치 {info.n_rms:.2f}) × {1 - wb:.0%}. "
            f"‘목록 안 위치’는 담은 곡들 중 가장 낮은 값을 0, 가장 높은 값을 1로 둔 값이에요.")


def placement(tid: str, *, current: list[str], original: list[str], suggested: list[str] | None,
              scores: dict[str, ScoreInfo], mode: str, curve, pin_first: str | None, pin_last: str | None,
              smooth: float, bpm_weight: float, stale: bool, bpm, rms) -> Placement:
    if stale:
        return Placement(stale=True, lines=["설정이 변경됐어요. 다시 추천하면 새 설정을 기준으로 배치 정보를 확인할 수 있어요."])
    n = len(current)
    i = current.index(tid)
    lo, hi = score_range(scores)
    target = float(target_curve(mode, n, lo, hi, curve)[i])      # 정렬·지표·그래프와 같은 목표값
    shape = target_shape(mode, n, curve)
    score = float(scores[tid].score)
    p = Placement(pos=i + 1, n=n, target=target, score=score, diff=abs(target - score))

    manual = bool(suggested) and current != suggested
    pinned_first = bool(pin_first) and tid == pin_first and i == 0
    pinned_last = bool(pin_last) and tid == pin_last and i == n - 1
    if pinned_first:
        p.lines.append("사용자가 첫 곡으로 고정했어요. 목표 점수와 차이가 있어도 이 위치를 유지해요.")
    elif pinned_last:
        p.lines.append("사용자가 마지막 곡으로 고정했어요. 목표 점수와 차이가 있어도 이 위치를 유지해요.")
    if manual:
        p.lines.append("사용자가 직접 순서를 변경했어요. 아래는 현재 위치의 목표 점수와 곡의 점수 비교예요.")

    p.lines.append(f"전체 {n}곡 중 {i + 1}번째예요. " + section_text(shape, i))
    t, sc, d = f"{target:.3f}", f"{score:.3f}", f"{abs(target - score):.3f}"
    p.lines.append(f"이 위치의 목표 점수는 {t}{igo(t)}, 이 곡의 흐름 점수는 {sc}{iyo(sc)}. 두 값의 차이는 {d}{iyo(d)}.")

    o = original.index(tid) + 1 if tid in original else None
    s = suggested.index(tid) + 1 if suggested and tid in suggested else None
    if manual:
        parts = [f"원래 순서 {o}번째" if o else None, f"마지막 추천 {s}번째" if s else None, f"지금 {i + 1}번째(직접 바꾼 순서)"]
        p.lines.append(" → ".join(x for x in parts if x) + ".")
    elif s is not None and o is not None:
        p.lines.append(f"원래 {o}번째였던 곡이 추천 순서에서는 {s}번째에 배치됐어요." if o != s
                       else f"원래 순서와 추천 순서 모두 {s}번째예요.")
    elif o is not None:
        p.lines.append(f"원래 순서 {o}번째, 지금 {i + 1}번째예요. 아직 추천 순서를 만들지 않았어요.")

    note = "정렬은 전체 곡의 배치와 설정을 함께 고려해요. 아래 값은 이 위치의 목표와 곡의 점수를 비교한 정보예요."
    if smooth > 0 and n > 2:
        note += f" ‘곡 사이 부드럽게 잇기’({smooth:.2f})도 함께 반영되어, 목표에 가장 가까운 곡이 항상 이 자리에 오지는 않아요."
    if hi - lo < 1e-12:
        note += " 지금은 모든 곡의 흐름 점수가 같아 순서에 따른 차이가 없어요."
    p.note = note
    p.formula = formula_text(scores[tid], bpm_weight, bpm, rms)
    return p
