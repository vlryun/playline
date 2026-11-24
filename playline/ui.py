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

from .arrange import MODES, target_shape

# 팔레트: 밤하늘 같은 짙은 배경 + 홀로그램 CD의 무지갯빛 + 투명 플라스틱 케이스
BG = "#07080C"
INK = "#EEF0F5"        # 본문 글자
MUTED = "#8E94A6"      # 보조 글자
LINE = "rgba(255,255,255,.12)"
SURFACE = "rgba(255,255,255,.035)"
CYAN = "#7CF7FF"
PINK = "#FF7AD9"
VIOLET = "#A98BFF"
AMBER = "#FFC46B"
MINT = "#9DFFB0"
HOLO = f"{CYAN}, {VIOLET}, {PINK}, {AMBER}, {MINT}, {CYAN}"
# 이전 이름 호환
GREEN, TERRA, CREAM = CYAN, PINK, BG

# 그래프 계열: 색 + 선 모양 + 점 모양을 함께 다르게 해서 색만으로 구분하지 않는다
SERIES_STYLE = {
    "원래 순서": {"color": "#7D8497", "dash": [6, 4], "shape": "circle"},
    "추천 순서": {"color": CYAN, "dash": [1, 0], "shape": "diamond"},
    "내가 바꾼 순서": {"color": PINK, "dash": [1, 0], "shape": "square"},
    "원하는 흐름": {"color": "#F4F4F8", "dash": [2, 3], "shape": "triangle-up"},
}
VERSION_STYLE = {"color": AMBER, "dash": [8, 3, 2, 3], "shape": "cross"}


def css() -> str:
    return f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,500;12..96,700;12..96,800&display=swap');

.pl-glow {{ position:fixed; inset:0; pointer-events:none; z-index:0;
  background:
    radial-gradient(600px 420px at 8% -6%, rgba(124,247,255,.16), transparent 70%),
    radial-gradient(520px 420px at 96% 4%, rgba(255,122,217,.14), transparent 70%),
    radial-gradient(700px 500px at 70% 110%, rgba(169,139,255,.12), transparent 70%); }}

.pl-hero {{ display:flex; align-items:center; gap:22px; padding:8px 0 4px; position:relative; z-index:1; }}
.pl-hero-disc {{ width:104px; height:104px; flex:none; border-radius:50%; position:relative;
  background:
    radial-gradient(circle at 50% 50%, {BG} 0 11%, rgba(255,255,255,.55) 11.5% 12.5%, transparent 13% 100%),
    radial-gradient(circle at 50% 50%, transparent 0 30%, rgba(255,255,255,.18) 30.5% 31%, transparent 31.5% 100%),
    repeating-radial-gradient(circle at 50% 50%, rgba(255,255,255,.07) 0 1px, transparent 1px 3px),
    conic-gradient(from 210deg, {HOLO});
  box-shadow: 0 0 0 1px rgba(255,255,255,.22), 0 18px 50px -12px rgba(124,247,255,.45), 0 10px 40px -10px rgba(255,122,217,.4);
  animation: pl-spin 14s linear infinite; }}
.pl-hero-disc::after {{ content:''; position:absolute; inset:0; border-radius:50%;
  background: linear-gradient(125deg, rgba(255,255,255,.55) 0%, transparent 28%, transparent 62%, rgba(255,255,255,.25) 100%);
  mix-blend-mode: overlay; }}
@keyframes pl-spin {{ to {{ transform: rotate(360deg); }} }}

.pl-logo {{ font-family:'Bricolage Grotesque','Noto Sans KR',sans-serif; font-weight:800; font-size:56px;
  letter-spacing:-2px; line-height:.95; color:{INK}; }}
.pl-slogan {{ font-family:'Bricolage Grotesque',sans-serif; font-weight:700; font-size:19px; letter-spacing:.2px;
  background: linear-gradient(90deg, {HOLO}); background-size:200% 100%; -webkit-background-clip:text; background-clip:text;
  color:transparent; animation: pl-sheen 9s ease-in-out infinite alternate; }}
@keyframes pl-sheen {{ from {{ background-position:0% 50%; }} to {{ background-position:100% 50%; }} }}
@media (prefers-reduced-motion: reduce) {{ .pl-hero-disc, .pl-slogan {{ animation:none; }} }}
.pl-intro {{ color:{MUTED}; font-size:15px; margin:4px 0 0; max-width:560px; }}
.pl-hero-text {{ display:flex; flex-direction:column; gap:4px; min-width:0; }}
.pl-eyebrow {{ font-size:11.5px; letter-spacing:2.4px; text-transform:uppercase; color:{MUTED}; font-weight:600; }}

.pl-step {{ display:flex; align-items:center; gap:9px; font-weight:700; font-size:15px; color:{INK}; margin:0 0 4px; }}
.pl-step .n {{ width:24px; height:24px; border-radius:50%; flex:none; display:inline-flex; align-items:center;
  justify-content:center; font-size:12px; color:{BG}; font-weight:800;
  background: conic-gradient(from 200deg, {HOLO}); box-shadow:0 0 14px -2px rgba(124,247,255,.5); }}
.pl-help {{ color:{MUTED}; font-size:12.5px; line-height:1.55; margin:0; }}

.pl-badge {{ display:inline-flex; align-items:center; gap:6px; padding:4px 11px; border-radius:999px;
  font-size:12.5px; font-weight:600; border:1px solid {LINE}; background:rgba(255,255,255,.04); color:{INK};
  white-space:nowrap; }}
.pl-badge.real {{ border-color:rgba(124,247,255,.45); color:{CYAN}; background:rgba(124,247,255,.07); }}
.pl-badge.demo {{ border-color:rgba(255,196,107,.5); color:{AMBER}; background:rgba(255,196,107,.08); }}
.pl-badge.edit {{ border-color:rgba(255,122,217,.5); color:{PINK}; background:rgba(255,122,217,.07); }}
.pl-badge.dot::before {{ content:''; width:7px; height:7px; border-radius:50%; background:currentColor;
  box-shadow:0 0 8px currentColor; }}
.pl-badges {{ display:flex; flex-wrap:wrap; gap:7px; align-items:center; }}

.pl-demo-note {{ border:1px solid rgba(255,196,107,.3); border-left:3px solid {AMBER}; background:rgba(255,196,107,.06);
  padding:9px 13px; border-radius:4px 10px 10px 4px; font-size:13px; color:#F3DDB6; line-height:1.55; }}

.pl-track {{ display:flex; align-items:center; gap:14px; min-width:0; width:100%; }}
.pl-pos {{ font-family:'Bricolage Grotesque',sans-serif; font-weight:800; font-size:20px; width:28px; text-align:right;
  flex:none; background: linear-gradient(180deg, #fff, #9AA3B8); -webkit-background-clip:text; background-clip:text;
  color:transparent; }}
/* 곡 커버: 곡마다 각도가 다른 홀로그램 디스크 (앨범 이미지 아님) */
.pl-cover {{ width:46px; height:46px; border-radius:50%; flex:none; position:relative;
  background:
    radial-gradient(circle at 50% 50%, {BG} 0 13%, rgba(255,255,255,.6) 13.5% 15%, transparent 15.5% 100%),
    repeating-radial-gradient(circle at 50% 50%, rgba(255,255,255,.08) 0 1px, transparent 1px 3px),
    conic-gradient(from var(--a, 0deg), {HOLO});
  box-shadow: 0 0 0 1px rgba(255,255,255,.18), 0 6px 18px -6px rgba(124,247,255,.35);
  transition: transform .6s cubic-bezier(.2,.7,.2,1); }}
.pl-cover::after {{ content:''; position:absolute; inset:0; border-radius:50%;
  background: linear-gradient(130deg, rgba(255,255,255,.5), transparent 35%, transparent 65%, rgba(255,255,255,.2));
  mix-blend-mode: overlay; }}
.pl-track:hover .pl-cover {{ transform: rotate(160deg); }}
.pl-meta {{ min-width:0; flex:1; }}
.pl-title {{ font-weight:700; font-size:15.5px; color:{INK}; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
.pl-sub {{ font-size:12.5px; color:{MUTED}; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; margin-top:2px; }}
.pl-nums {{ display:flex; gap:14px; flex:none; font-size:12.5px; color:{MUTED}; font-variant-numeric:tabular-nums; }}
.pl-nums b {{ color:{INK}; font-weight:600; }}
.pl-nums > span {{ display:inline-block; white-space:nowrap; }}
.pl-nums > span:nth-child(1) {{ width:62px; }}
.pl-nums > span:nth-child(2) {{ width:80px; }}
.pl-nums > span:nth-child(3) {{ width:84px; }}
.pl-nums > span:nth-child(4) {{ width:124px; }}
@media (max-width: 1440px) {{ .pl-nums > span:nth-child(1), .pl-nums > span:nth-child(3) {{ display:none; }} }}
.pl-bar {{ width:56px; height:5px; border-radius:3px; background:rgba(255,255,255,.1); overflow:hidden; display:inline-block;
  vertical-align:middle; margin-left:5px; }}
.pl-bar > i {{ display:block; height:100%; background: linear-gradient(90deg, {CYAN}, {VIOLET}, {PINK});
  box-shadow:0 0 8px rgba(124,247,255,.6); }}
.pl-tag {{ font-size:11px; padding:1px 7px; border-radius:999px; border:1px solid {LINE}; color:{MUTED}; margin-left:7px;
  font-weight:500; vertical-align:1px; }}
.pl-tag.lock {{ border-color:rgba(124,247,255,.5); color:{CYAN}; }}
.pl-tag.warn {{ border-color:rgba(255,196,107,.5); color:{AMBER}; }}
.pl-moved-up {{ color:{CYAN}; }} .pl-moved-down {{ color:{PINK}; }}

.pl-mode {{ display:flex; gap:10px; align-items:center; min-width:0; }}
.pl-mode b {{ font-size:14.5px; color:{INK}; }}
.pl-mode p {{ margin:1px 0 0; font-size:12.5px; color:{MUTED}; line-height:1.4; }}

.pl-empty {{ position:relative; border:1px solid {LINE}; border-radius:18px; padding:30px 26px; overflow:hidden;
  background: linear-gradient(160deg, rgba(255,255,255,.05), rgba(255,255,255,.01)); }}
.pl-empty::before {{ content:''; position:absolute; right:-90px; top:-90px; width:260px; height:260px; border-radius:50%;
  background:
    radial-gradient(circle, {BG} 0 12%, transparent 12.5% 100%),
    repeating-radial-gradient(circle, rgba(255,255,255,.07) 0 1px, transparent 1px 3px),
    conic-gradient(from 120deg, {HOLO}); opacity:.35; }}
.pl-empty h3 {{ margin:0 0 8px; font-size:22px; color:{INK}; position:relative; }}
.pl-empty p, .pl-empty ol {{ position:relative; }}
.pl-empty ol {{ margin:10px 0 0 18px; padding:0; color:{MUTED}; font-size:14px; line-height:1.9; }}
.pl-empty ol b {{ color:{INK}; }}
.pl-section {{ display:flex; align-items:center; gap:12px; margin:8px 0 4px; }}
.pl-section h4 {{ margin:0; font-size:18px; font-weight:700; color:{INK}; letter-spacing:-.2px; }}
.pl-section .ln {{ flex:1; height:1px; background: linear-gradient(90deg, rgba(124,247,255,.5), rgba(255,122,217,.25), transparent); }}
.pl-note {{ font-size:12.5px; color:{MUTED}; line-height:1.6; }}

/* st.container(key=...) 가 붙이는 공식 클래스 — 투명 플라스틱 케이스 느낌 */
.st-key-panel {{ position:relative; border-radius:18px; padding:16px 15px 10px;
  background: linear-gradient(170deg, rgba(255,255,255,.065), rgba(255,255,255,.015) 40%, rgba(255,255,255,.03));
  border:1px solid rgba(255,255,255,.14);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.14), inset 0 -1px 0 rgba(0,0,0,.4), 0 30px 60px -30px rgba(0,0,0,.8); }}
.st-key-focus_upload {{ outline:2px solid {PINK}; outline-offset:4px; border-radius:12px; }}
[class*="st-key-trackrow_"] {{ border-radius:14px; padding:7px 8px; border:1px solid transparent;
  transition: background .2s, border-color .2s; }}
[class*="st-key-trackrow_"]:hover {{ background:rgba(255,255,255,.04); border-color:rgba(255,255,255,.1); }}
[class*="st-key-modecard_"] {{ border:1px solid {LINE}; border-radius:12px; padding:3px 6px 3px 10px;
  background:rgba(255,255,255,.025); transition: border-color .2s, background .2s; }}
[class*="st-key-modecard_"]:hover {{ border-color:rgba(255,255,255,.28); background:rgba(255,255,255,.05); }}
.pl-mode-desc {{ margin:8px 2px 0; color:{INK}; opacity:.8; }}
[class*="st-key-modecard_sel_"] {{ border:1px solid transparent;
  background: linear-gradient(#0E1018, #0E1018) padding-box, linear-gradient(120deg, {HOLO}) border-box;
  box-shadow: 0 0 22px -8px rgba(124,247,255,.55); }}

.pl-mobile-only {{ display:none; }}
@media (max-width: 640px) {{
  .pl-mobile-only {{ display:block; }}
  .pl-hero {{ gap:14px; }}
  .pl-hero-disc {{ width:64px; height:64px; }}
  .pl-logo {{ font-size:38px; letter-spacing:-1.2px; }}
  .pl-nums {{ display:none; }}
  .pl-cover {{ width:34px; height:34px; }}
  .pl-pos {{ width:18px; font-size:16px; }}
  .pl-track {{ gap:9px; }}
}}
</style>
<div class="pl-glow" aria-hidden="true"></div>
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
    for mode in MODES:
        for state, color in (("on", CYAN), ("off", "#5B6173")):
            rules.append(f'.pl-curve-{mode}-{state}{{width:58px;height:30px;flex:none;'
                         f'background:url("{svg_data_uri(mode_svg(mode, color=color))}") center/contain no-repeat;}}')
    return "<style>" + " ".join(rules) + "</style>"


def esc(s) -> str:
    return html.escape("" if s is None else str(s))


def logo_svg(size: int = 30) -> str:
    # 브랜드 요소: 세 점을 잇는 작은 흐름 곡선 (분석 그래프가 아님)
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 32 32" aria-hidden="true">'
            f'<defs><linearGradient id="g" x1="0" x2="1"><stop offset="0" stop-color="{CYAN}"/>'
            f'<stop offset=".5" stop-color="{VIOLET}"/><stop offset="1" stop-color="{PINK}"/></linearGradient></defs>'
            f'<path d="M4 24 C 11 24, 12 9, 17 9 S 24 20, 28 12" fill="none" stroke="url(#g)" '
            f'stroke-width="3" stroke-linecap="round"/>'
            f'<circle cx="4" cy="24" r="3" fill="{CYAN}"/><circle cx="17" cy="9" r="3" fill="{VIOLET}"/>'
            f'<circle cx="28" cy="12" r="3" fill="{PINK}"/></svg>')


def hero_html() -> str:
    return """
<div class="pl-hero">
  <div class="pl-hero-disc" role="img" aria-label="PLAYLINE 디스크 로고"></div>
  <div class="pl-hero-text">
    <div class="pl-eyebrow">Playlist flow studio</div>
    <div class="pl-logo">PLAYLINE</div>
    <div class="pl-slogan">Your tracks. Your flow.</div>
    <p class="pl-intro">좋아하는 곡에, 나만의 흐름을. 곡을 고르고 원하는 분위기 흐름을 정하면 듣기 좋은 순서를 추천해 드려요.</p>
  </div>
</div>
"""


def step_html(n: int, title: str) -> str:
    return f'<div class="pl-step"><span class="n">{n}</span>{esc(title)}</div>'


def section_html(title: str) -> str:
    return f'<div class="pl-section"><h4>{esc(title)}</h4><span class="ln"></span></div>'


def mode_svg(mode: str, w: int = 58, h: int = 30, color: str = CYAN) -> str:
    ys = target_shape(mode, 21)
    pts = " ".join(f"{3 + i * (w - 6) / 20:.1f},{h - 4 - y * (h - 8):.1f}" for i, y in enumerate(ys))
    return (f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" aria-hidden="true">'
            f'<line x1="3" y1="{h - 2}" x2="{w - 3}" y2="{h - 2}" stroke="#3A3F50" stroke-width="1"/>'
            f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2.4" '
            f'stroke-linecap="round" stroke-linejoin="round"/></svg>')


def mode_curve_html(mode: str, label: str, selected: bool) -> str:
    return (f'<span class="pl-curve-{mode}-{"on" if selected else "off"}" role="img" '
            f'aria-label="{esc(label)} 곡선 미리보기" style="display:block"></span>')


def mode_card_html(mode: str, label: str, desc: str, selected: bool) -> str:
    return (f'<div class="pl-mode"><span class="pl-curve-{mode}-{"on" if selected else "off"}" role="img" '
            f'aria-label="{esc(label)} 곡선 미리보기"></span>'
            f'<div><b>{esc(label)}</b>{f"<p>{esc(desc)}</p>" if desc else ""}</div></div>')


def cover_html(track: dict) -> str:
    """곡마다 각도가 다른 홀로그램 디스크 타일 (앨범 이미지가 아닌 장식)."""
    key = track.get("sha256") or track["id"]
    angle = int(hashlib.md5(key.encode("utf-8")).hexdigest(), 16) % 360
    return f'<div class="pl-cover" style="--a:{angle}deg" aria-hidden="true"></div>'


def fmt_duration(sec) -> str:
    if sec is None:
        return "—"
    sec = int(round(sec))
    return f"{sec // 60}:{sec % 60:02d}"


def track_row_html(pos: int, track: dict, bpm, score: float, *, demo: bool, locked: bool,
                   orig_pos: int | None, has_audio: bool) -> str:
    tags = ""
    if locked:
        tags += '<span class="pl-tag lock">자리 고정</span>'
    if track.get("status") == "bpm_failed" or bpm is None:
        tags += '<span class="pl-tag warn">빠르기 못 잼 · 소리 크기만 사용</span>'
    elif track.get("bpm_factor", 1.0) != 1.0:
        tags += f'<span class="pl-tag">빠르기 ×{track["bpm_factor"]:g}</span>'
    if demo:
        tags += '<span class="pl-tag warn">예시 값</span>'

    parts = []
    if track.get("artist"):
        parts.append(esc(track["artist"]))
    if demo and track.get("category"):
        parts.append(esc(track["category"]))
    if not demo:
        if track.get("source") != "library":
            parts.append(esc(track.get("filename") or ""))
        if track.get("source") == "library":
            parts.append("라이브러리" if has_audio else "라이브러리 · 듣기 불가")
        elif not has_audio:
            parts.append("음악 파일 없음")
    if orig_pos is not None and orig_pos != pos:
        cls = "pl-moved-up" if orig_pos > pos else "pl-moved-down"
        parts.append(f'<span class="{cls}">원래 {orig_pos}번째</span>')
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
    <div class="pl-sub pl-mobile-only">빠르기 {bpm_txt} · 소리 {rms_txt} · 흐름 {score:.2f}</div>
  </div>
  <div class="pl-nums">
    <span>길이 <b>{fmt_duration(track.get('duration_sec'))}</b></span>
    <span title="1분당 박자 수(BPM)">빠르기 <b>{bpm_txt}</b></span>
    <span title="평균 소리 세기(RMS)">소리 <b>{rms_txt}</b></span>
    <span title="빠르기와 소리 크기를 합친 점수 (이 목록 안에서 비교한 값)">흐름 <b>{score:.2f}</b><span class="pl-bar"><i style="width:{bar:.0f}%"></i></span></span>
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
                         "짧은 곡명": short(t["title"]), "빠르기": raw[tid]["bpm"], "소리 크기": raw[tid]["rms"],
                         "흐름 점수": raw[tid]["score"]})
    if target is not None:
        for i, v in enumerate(target, start=1):
            rows.append({"계열": "원하는 흐름", "순서": i, "값": float(v), "곡명": "(원하는 흐름)",
                         "짧은 곡명": "", "빠르기": None, "소리 크기": None, "흐름 점수": float(v)})
    df = pd.DataFrame(rows)

    names = list(series) + (["원하는 흐름"] if target is not None else [])
    styles = [SERIES_STYLE.get(n, VERSION_STYLE) for n in names]
    color = alt.Color("계열:N", scale=alt.Scale(domain=names, range=[s["color"] for s in styles]),
                      legend=alt.Legend(title=None, orient="bottom", direction="horizontal", symbolStrokeWidth=2.5,
                                        labelFontSize=12.5, symbolSize=110, columns=4))
    dash = alt.StrokeDash("계열:N", scale=alt.Scale(domain=names, range=[s["dash"] for s in styles]), legend=None)
    shape = alt.Shape("계열:N", scale=alt.Scale(domain=names, range=[s["shape"] for s in styles]), legend=None)
    n = int(df["순서"].max()) if len(df) else 1
    x = alt.X("순서:Q", title="재생 순서 (점 하나 = 곡 하나)", scale=alt.Scale(domain=[0.7, n + 0.3], nice=False),
              axis=alt.Axis(values=list(range(1, n + 1)), format="d", tickMinStep=1, grid=False))
    y = alt.Y("값:Q", title=metric_label, scale=alt.Scale(domain=list(domain), nice=False, zero=False))
    tooltip = [alt.Tooltip("계열:N"), alt.Tooltip("순서:Q"), alt.Tooltip("곡명:N"),
               alt.Tooltip("빠르기:Q", format=".1f"), alt.Tooltip("소리 크기:Q", format=".4f"),
               alt.Tooltip("흐름 점수:Q", format=".2f")]

    base = alt.Chart(df).encode(x=x, y=y, color=color, strokeDash=dash, tooltip=tooltip)
    lines = base.mark_line(strokeWidth=2.4, interpolate="linear")
    points = base.mark_point(filled=True, size=64, opacity=1).encode(shape=shape)
    chart = (lines + points).properties(height=320).configure(
        font="Noto Sans KR", background="transparent",
    ).configure_axis(
        labelColor=MUTED, titleColor=MUTED, gridColor="rgba(255,255,255,.07)", domainColor="#2A2F3D",
        tickColor="#2A2F3D",
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
