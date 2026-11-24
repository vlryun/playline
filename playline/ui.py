# [AI 보조 도구: Claude Code (Claude Opus 5.5), 작업: 'PLAYLINE 화면 스타일·HTML 조각·비교 그래프 구성']
"""화면 구성 도우미 (스타일, HTML 조각, 그래프).

스타일은 이 파일에서 만든 HTML 요소의 자체 클래스(.pl-*)와, st.container(key=...)가
공식적으로 붙여 주는 .st-key-* 클래스에만 적용한다. Streamlit 내부 구조 선택자에는
의존하지 않는다. 기본 색·글꼴·모서리는 .streamlit/config.toml 테마에서 정한다.
"""

from __future__ import annotations

import base64
import hashlib
import html

import altair as alt
import numpy as np
import pandas as pd

from .arrange import target_shape

CREAM = "#F5F1E8"
INK = "#252A29"
GREEN = "#31594D"
TERRA = "#CB765D"
LINE = "#DDD6C9"
MUTED = "#6E716C"
SURFACE = "#FBF8F2"

# 그래프 계열: 색 + 선 모양 + 점 모양을 함께 다르게 해서 색만으로 구분하지 않는다
SERIES_STYLE = {
    "원본 순서": {"color": "#9A9184", "dash": [6, 4], "shape": "circle"},
    "자동 제안": {"color": GREEN, "dash": [1, 0], "shape": "diamond"},
    "직접 수정": {"color": TERRA, "dash": [1, 0], "shape": "square"},
    "목표 곡선": {"color": INK, "dash": [2, 3], "shape": "triangle-up"},
}
VERSION_STYLE = {"color": "#6F7FA0", "dash": [8, 3, 2, 3], "shape": "cross"}

COVER_COLORS = ["#31594D", "#CB765D", "#8C6D46", "#5E7A6E", "#A3553F", "#3F4F4A", "#B48A5A", "#6B5A4E"]


def css() -> str:
    return f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,700;12..96,800&display=swap');

.pl-hero {{ display:flex; flex-wrap:wrap; align-items:flex-end; gap:6px 28px; padding:4px 0 2px; }}
.pl-logo {{ font-family:'Bricolage Grotesque','Noto Sans KR',sans-serif; font-weight:800; font-size:44px;
  letter-spacing:-1.5px; line-height:1; color:{INK}; display:flex; align-items:center; gap:10px; }}
.pl-logo svg {{ flex:none; }}
.pl-slogan {{ font-family:'Bricolage Grotesque',sans-serif; font-weight:700; color:{GREEN}; font-size:18px; }}
.pl-intro {{ color:{MUTED}; font-size:15px; margin:2px 0 0; }}
.pl-hero-text {{ display:flex; flex-direction:column; gap:2px; padding-bottom:3px; }}

.pl-step {{ display:flex; align-items:center; gap:8px; font-weight:700; font-size:15px; color:{INK}; margin:0 0 2px; }}
.pl-step .n {{ width:22px; height:22px; border-radius:50%; border:1.5px solid {GREEN}; color:{GREEN};
  display:inline-flex; align-items:center; justify-content:center; font-size:12px; flex:none; }}
.pl-help {{ color:{MUTED}; font-size:13px; line-height:1.5; margin:0; }}

.pl-badge {{ display:inline-flex; align-items:center; gap:6px; padding:3px 10px; border-radius:999px;
  font-size:12.5px; font-weight:600; border:1px solid {LINE}; background:{SURFACE}; color:{INK}; white-space:nowrap; }}
.pl-badge.real {{ border-color:{GREEN}; color:{GREEN}; }}
.pl-badge.demo {{ border-color:{TERRA}; color:#A5523B; background:#FBEEE8; }}
.pl-badge.edit {{ border-color:{TERRA}; color:#A5523B; }}
.pl-badge.dot::before {{ content:''; width:7px; height:7px; border-radius:50%; background:currentColor; }}
.pl-badges {{ display:flex; flex-wrap:wrap; gap:6px; align-items:center; }}

.pl-demo-note {{ border-left:3px solid {TERRA}; background:#FBEEE8; padding:8px 12px; border-radius:0 8px 8px 0;
  font-size:13px; color:#6B3A2C; line-height:1.5; }}

.pl-track {{ display:flex; align-items:center; gap:12px; min-width:0; width:100%; }}
.pl-pos {{ font-family:'Bricolage Grotesque',sans-serif; font-weight:800; font-size:18px; width:26px; text-align:right;
  color:{GREEN}; flex:none; }}
.pl-cover {{ width:42px; height:42px; border-radius:8px; flex:none; display:flex; align-items:flex-end;
  justify-content:flex-start; padding:4px 5px; color:{CREAM}; font-weight:800; font-size:15px; line-height:1;
  font-family:'Bricolage Grotesque','Noto Sans KR',sans-serif; position:relative; overflow:hidden; }}
.pl-cover::after {{ content:''; position:absolute; right:-10px; top:-10px; width:30px; height:30px; border-radius:50%;
  border:2px solid rgba(245,241,232,.55); }}
.pl-meta {{ min-width:0; flex:1; }}
.pl-title {{ font-weight:700; font-size:15.5px; color:{INK}; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
.pl-sub {{ font-size:12.5px; color:{MUTED}; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; margin-top:1px; }}
.pl-nums {{ display:flex; gap:14px; flex:none; font-size:12.5px; color:{MUTED}; font-variant-numeric:tabular-nums; }}
.pl-nums b {{ color:{INK}; font-weight:600; }}
.pl-nums > span {{ display:inline-block; white-space:nowrap; }}
.pl-nums > span:nth-child(1) {{ width:62px; }}
.pl-nums > span:nth-child(2) {{ width:76px; }}
.pl-nums > span:nth-child(3) {{ width:84px; }}
.pl-nums > span:nth-child(4) {{ width:112px; }}
@media (max-width: 1180px) {{ .pl-nums > span:nth-child(1), .pl-nums > span:nth-child(3) {{ display:none; }} }}
.pl-bar {{ width:54px; height:6px; border-radius:3px; background:{LINE}; overflow:hidden; display:inline-block;
  vertical-align:middle; margin-left:4px; }}
.pl-bar > i {{ display:block; height:100%; background:{GREEN}; }}
.pl-tag {{ font-size:11px; padding:1px 6px; border-radius:4px; border:1px solid {LINE}; color:{MUTED}; margin-left:6px;
  font-weight:500; vertical-align:1px; }}
.pl-tag.lock {{ border-color:{GREEN}; color:{GREEN}; }}
.pl-tag.warn {{ border-color:{TERRA}; color:#A5523B; }}
.pl-moved-up {{ color:{GREEN}; }} .pl-moved-down {{ color:#A5523B; }}

.pl-mode {{ display:flex; gap:10px; align-items:center; min-width:0; }}
.pl-mode svg {{ flex:none; }}
.pl-mode b {{ font-size:14.5px; }}
.pl-mode p {{ margin:1px 0 0; font-size:12.5px; color:{MUTED}; line-height:1.4; }}

.pl-empty {{ border:1px dashed {LINE}; border-radius:12px; padding:28px 22px; background:{SURFACE}; }}
.pl-empty h3 {{ margin:0 0 6px; font-size:19px; }}
.pl-empty ol {{ margin:8px 0 0 18px; padding:0; color:{MUTED}; font-size:14px; line-height:1.8; }}
.pl-section {{ display:flex; align-items:center; gap:10px; margin:6px 0 2px; }}
.pl-section h4 {{ margin:0; font-size:17px; font-weight:700; }}
.pl-section .ln {{ flex:1; height:1px; background:{LINE}; }}
.pl-note {{ font-size:12.5px; color:{MUTED}; line-height:1.55; }}

/* st.container(key=...) 가 붙이는 공식 클래스 */
.st-key-panel {{ background:{SURFACE}; border:1px solid {LINE}; border-radius:12px; padding:14px 14px 8px;
  box-shadow:0 1px 2px rgba(37,42,41,.04); }}
.st-key-focus_upload {{ outline:2px solid {TERRA}; outline-offset:4px; border-radius:10px; }}
[class*="st-key-trackrow_"] {{ border-bottom:1px solid {LINE}; padding:6px 2px; }}
[class*="st-key-modecard_"] {{ border:1px solid {LINE}; border-radius:10px; padding:8px 10px; background:#fff8; }}
[class*="st-key-modecard_sel_"] {{ border-color:{GREEN}; box-shadow:inset 3px 0 0 {GREEN}; background:#fff; }}

.pl-mobile-only {{ display:none; }}
@media (max-width: 640px) {{
  .pl-mobile-only {{ display:block; }}
  .pl-logo {{ font-size:34px; }}
  .pl-nums {{ display:none; }}
  .pl-cover {{ display:none; }}
  .pl-pos {{ width:18px; font-size:16px; }}
  .pl-track {{ gap:8px; }}
}}
</style>
"""


def svg_data_uri(svg: str) -> str:
    """st.html은 <svg>·<img>를 걸러내므로, 곡선 그림은 CSS 배경 이미지(data URI)로 넣는다."""
    if "xmlns" not in svg:
        svg = svg.replace("<svg ", '<svg xmlns="http://www.w3.org/2000/svg" ', 1)
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode("ascii")


def icon_css() -> str:
    """브랜드 곡선과 흐름 모드 미리보기 곡선을 CSS 클래스로 만든다."""
    rules = [f'.pl-logo-mark{{width:36px;height:36px;flex:none;background:url("{svg_data_uri(logo_svg(36))}") '
             f'center/contain no-repeat;}}']
    for mode in ("rise", "fall", "arc"):
        for state, color in (("on", GREEN), ("off", "#8C8577")):
            rules.append(f'.pl-curve-{mode}-{state}{{width:58px;height:30px;flex:none;'
                         f'background:url("{svg_data_uri(mode_svg(mode, color=color))}") center/contain no-repeat;}}')
    return "<style>" + " ".join(rules) + "</style>"


def esc(s) -> str:
    return html.escape("" if s is None else str(s))


def logo_svg(size: int = 30) -> str:
    # 브랜드 요소: 세 점을 잇는 작은 흐름 곡선 (분석 그래프가 아님)
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 32 32" aria-hidden="true">'
            f'<path d="M4 24 C 11 24, 12 9, 17 9 S 24 20, 28 12" fill="none" stroke="{TERRA}" '
            f'stroke-width="3" stroke-linecap="round"/>'
            f'<circle cx="4" cy="24" r="3" fill="{GREEN}"/><circle cx="17" cy="9" r="3" fill="{GREEN}"/>'
            f'<circle cx="28" cy="12" r="3" fill="{GREEN}"/></svg>')


def hero_html() -> str:
    return f"""
<div class="pl-hero">
  <div class="pl-logo"><span class="pl-logo-mark" role="img" aria-label="PLAYLINE 로고"></span>PLAYLINE</div>
  <div class="pl-hero-text">
    <div class="pl-slogan">Your tracks. Your flow.</div>
    <p class="pl-intro">좋아하는 곡에, 나만의 흐름을. 곡을 넣고 원하는 흐름을 고르면 순서를 제안하고, 전후를 비교해 직접 고칠 수 있어요.</p>
  </div>
</div>
"""


def step_html(n: int, title: str) -> str:
    return f'<div class="pl-step"><span class="n">{n}</span>{esc(title)}</div>'


def section_html(title: str) -> str:
    return f'<div class="pl-section"><h4>{esc(title)}</h4><span class="ln"></span></div>'


def mode_svg(mode: str, w: int = 58, h: int = 30, color: str = GREEN) -> str:
    ys = target_shape(mode, 21)
    pts = " ".join(f"{3 + i * (w - 6) / 20:.1f},{h - 4 - y * (h - 8):.1f}" for i, y in enumerate(ys))
    return (f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" aria-hidden="true">'
            f'<line x1="3" y1="{h - 2}" x2="{w - 3}" y2="{h - 2}" stroke="{LINE}" stroke-width="1"/>'
            f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2.4" '
            f'stroke-linecap="round" stroke-linejoin="round"/></svg>')


def mode_card_html(mode: str, label: str, desc: str, selected: bool) -> str:
    return (f'<div class="pl-mode"><span class="pl-curve-{mode}-{"on" if selected else "off"}" role="img" '
            f'aria-label="{esc(label)} 곡선 미리보기"></span>'
            f'<div><b>{esc(label)}</b><p>{esc(desc)}</p></div></div>')


def cover_html(track: dict) -> str:
    key = track.get("sha256") or track["id"]
    idx = int(hashlib.md5(key.encode("utf-8")).hexdigest(), 16) % len(COVER_COLORS)
    title = (track.get("title") or "?").strip()
    initial = title[:1].upper() if title else "?"
    return f'<div class="pl-cover" style="background:{COVER_COLORS[idx]}" aria-hidden="true">{esc(initial)}</div>'


def fmt_duration(sec) -> str:
    if sec is None:
        return "—"
    sec = int(round(sec))
    return f"{sec // 60}:{sec % 60:02d}"


def track_row_html(pos: int, track: dict, bpm, score: float, *, demo: bool, locked: bool,
                   orig_pos: int | None, has_audio: bool) -> str:
    tags = ""
    if locked:
        tags += '<span class="pl-tag lock">고정</span>'
    if track.get("status") == "bpm_failed" or bpm is None:
        tags += '<span class="pl-tag warn">BPM 추정 실패 · RMS만 사용</span>'
    elif track.get("bpm_factor", 1.0) != 1.0:
        tags += f'<span class="pl-tag">BPM ×{track["bpm_factor"]:g} 해석</span>'
    if demo:
        tags += '<span class="pl-tag warn">가상값</span>'

    parts = []
    if track.get("artist"):
        parts.append(esc(track["artist"]))
    if demo and track.get("category"):
        parts.append(esc(track["category"]))
    if not demo:
        if track.get("source") != "library":
            parts.append(esc(track.get("filename") or ""))
        if track.get("source") == "library":
            parts.append("라이브러리" if has_audio else "라이브러리 · 분석값만")
        elif not has_audio:
            parts.append("음원 미연결")
    if orig_pos is not None and orig_pos != pos:
        cls = "pl-moved-up" if orig_pos > pos else "pl-moved-down"
        parts.append(f'<span class="{cls}">원래 {orig_pos}번</span>')
    sub = " · ".join(p for p in parts if p)

    bpm_txt = "—" if bpm is None else f"{bpm:.1f}"
    rms_txt = "—" if track.get("rms") is None else f"{track['rms']:.4f}"
    bar = max(0.0, min(1.0, score)) * 100
    return f"""
<div class="pl-track">
  <div class="pl-pos">{pos}</div>
  {cover_html(track)}
  <div class="pl-meta">
    <div class="pl-title" title="{esc(track.get('title'))}">{esc(track.get('title'))}{tags}</div>
    <div class="pl-sub">{sub}</div>
    <div class="pl-sub pl-mobile-only">BPM {bpm_txt} · RMS {rms_txt} · 흐름 {score:.2f}</div>
  </div>
  <div class="pl-nums">
    <span>길이 <b>{fmt_duration(track.get('duration_sec'))}</b></span>
    <span>BPM <b>{bpm_txt}</b></span>
    <span>RMS <b>{rms_txt}</b></span>
    <span title="같은 목록 안에서의 상대적 배열 지표">흐름 <b>{score:.2f}</b><span class="pl-bar"><i style="width:{bar:.0f}%"></i></span></span>
  </div>
</div>
"""


def short(title: str, n: int = 16) -> str:
    title = title or ""
    return title if len(title) <= n else title[: n - 1] + "…"


def flow_chart(series: dict[str, list[str]], tracks: dict[str, dict], values: dict[str, float],
               metric_label: str, domain: tuple[float, float], target: list[float] | None,
               raw: dict[str, dict]) -> alt.Chart:
    """곡별 대표값을 순서대로 이은 비교 그래프.

    series : 계열 이름 → 곡 id 순서
    values : 곡 id → 그래프에 쓸 값 (모든 계열에 같은 값을 쓰므로 같은 기준이 유지됨)
    """
    rows = []
    for name, order in series.items():
        for i, tid in enumerate(order, start=1):
            t = tracks[tid]
            rows.append({"계열": name, "순서": i, "값": values[tid], "곡명": t["title"],
                         "짧은 곡명": short(t["title"]), "BPM": raw[tid]["bpm"], "RMS": raw[tid]["rms"],
                         "흐름 점수": raw[tid]["score"]})
    if target is not None:
        for i, v in enumerate(target, start=1):
            rows.append({"계열": "목표 곡선", "순서": i, "값": float(v), "곡명": "(목표 위치)",
                         "짧은 곡명": "", "BPM": None, "RMS": None, "흐름 점수": float(v)})
    df = pd.DataFrame(rows)

    names = list(series) + (["목표 곡선"] if target is not None else [])
    styles = [SERIES_STYLE.get(n, VERSION_STYLE) for n in names]
    color = alt.Color("계열:N", scale=alt.Scale(domain=names, range=[s["color"] for s in styles]),
                      legend=alt.Legend(title=None, orient="bottom", direction="horizontal", symbolStrokeWidth=2.5,
                                        labelFontSize=12.5, symbolSize=110, columns=4))
    dash = alt.StrokeDash("계열:N", scale=alt.Scale(domain=names, range=[s["dash"] for s in styles]), legend=None)
    shape = alt.Shape("계열:N", scale=alt.Scale(domain=names, range=[s["shape"] for s in styles]), legend=None)
    n = int(df["순서"].max()) if len(df) else 1
    x = alt.X("순서:Q", title="재생 순서 (곡 하나 = 점 하나)", scale=alt.Scale(domain=[0.7, n + 0.3], nice=False),
              axis=alt.Axis(values=list(range(1, n + 1)), format="d", tickMinStep=1, grid=False))
    y = alt.Y("값:Q", title=metric_label, scale=alt.Scale(domain=list(domain), nice=False, zero=False))
    tooltip = [alt.Tooltip("계열:N"), alt.Tooltip("순서:Q"), alt.Tooltip("곡명:N"),
               alt.Tooltip("BPM:Q", format=".1f"), alt.Tooltip("RMS:Q", format=".4f"),
               alt.Tooltip("흐름 점수:Q", format=".2f")]

    base = alt.Chart(df).encode(x=x, y=y, color=color, strokeDash=dash, tooltip=tooltip)
    lines = base.mark_line(strokeWidth=2.4, interpolate="linear")
    points = base.mark_point(filled=True, size=64, opacity=1).encode(shape=shape)
    chart = (lines + points).properties(height=320).configure(
        font="Noto Sans KR", background="transparent",
    ).configure_axis(
        labelColor=MUTED, titleColor=MUTED, gridColor="#E9E3D7", domainColor=LINE, tickColor=LINE,
        labelFontSize=12, titleFontSize=12, titleFontWeight="normal",
    ).configure_view(stroke=None).configure_legend(labelColor=INK)
    return chart


def raw_table(order: list[str], tracks: dict[str, dict], raw: dict[str, dict]) -> pd.DataFrame:
    return pd.DataFrame([{"순서": i, "곡명": tracks[t]["title"], "BPM": raw[t]["bpm"], "RMS": raw[t]["rms"],
                          "흐름 점수": round(raw[t]["score"], 3)} for i, t in enumerate(order, start=1)])


def padded_domain(vals: list[float], pad_ratio: float = 0.08) -> tuple[float, float]:
    vals = [v for v in vals if v is not None and np.isfinite(v)]
    if not vals:
        return (0.0, 1.0)
    lo, hi = min(vals), max(vals)
    if hi - lo < 1e-9:
        d = abs(lo) * 0.1 or 1.0
        return (lo - d, hi + d)
    p = (hi - lo) * pad_ratio
    return (lo - p, hi + p)
