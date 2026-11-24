# [AI 보조 도구: Claude Code (Claude Opus 5.5), 작업: '나만의 흐름 곡선 편집기 (Streamlit components v2)']
"""'✏️ 나만의 흐름' 곡선 편집기.

- 직접 그리기: 누른 채 움직여(마우스·터치) 흐름을 그린다. 그린 구간만 바뀌고 나머지는 원래 곡선을 유지한다.
- 점으로 다듬기: 조절점을 위아래로 끈다. 가로 위치는 고정이라 점의 순서가 뒤집히지 않는다.
- 두 방식은 같은 곡선 데이터([[x, y], ...], x·y 모두 0~1)를 고친다.
- 드래그하는 동안은 편집기 안에서만 다시 그리고, 손을 뗄 때 한 번만 Python 으로 곡선을 보낸다
  (매 움직임마다 앱 전체를 다시 실행하지 않음).
- 실행 취소·초기화·기존 흐름에서 시작은 편집기 안에서 처리한 뒤 같은 방식으로 곡선을 보낸다.
- 화면에 그리는 선은 점 사이를 곧게 잇는다. 정렬에 쓰는 목표값(선형 보간)과 모양이 같다.
"""

from __future__ import annotations

import streamlit as st

GRID = 13          # 직접 그린 뒤의 조절점 개수 (가로 등간격)

CSS = r"""
:host { display:block; }
.ce { font-family: 'Noto Sans KR', sans-serif; color:#EEF0F5; }
.ce-bar { display:flex; flex-wrap:wrap; gap:6px; align-items:center; margin:0 0 8px; }
.ce-tabs { display:inline-flex; padding:3px; border-radius:999px; background:rgba(255,255,255,.06); border:1px solid rgba(255,255,255,.12); }
.ce-tabs button { border:0; background:transparent; color:#8E94A6; font:inherit; font-size:12.5px; font-weight:700;
  padding:5px 12px; border-radius:999px; cursor:pointer; }
.ce-tabs button.on { color:#07080C; background:linear-gradient(90deg,#7CF7FF,#A98BFF); }
.ce-btn { border:1px solid rgba(255,255,255,.16); background:rgba(255,255,255,.05); color:#EEF0F5; font:inherit;
  font-size:12px; padding:5px 11px; border-radius:999px; cursor:pointer; }
.ce-btn:hover { background:rgba(255,255,255,.1); }
.ce-btn:disabled { opacity:.4; cursor:default; }
.ce select { background:rgba(255,255,255,.06); color:#EEF0F5; border:1px solid rgba(255,255,255,.16); border-radius:999px;
  padding:5px 8px; font:inherit; font-size:12px; }
.ce select option { background:#141722; }
.ce-wrap { position:relative; border-radius:14px; border:1px solid rgba(255,255,255,.12);
  background:linear-gradient(170deg, rgba(255,255,255,.05), rgba(255,255,255,.015)); overflow:hidden; }
.ce svg { display:block; width:100%; height:auto; touch-action:none; cursor:crosshair; user-select:none; }
.ce svg.pts { cursor:default; }
.ce .handle { cursor:ns-resize; }
.ce-help { font-size:12px; color:#8E94A6; margin:6px 2px 0; line-height:1.5; }
.ce-sp { flex:1; }
button:focus-visible, select:focus-visible { outline:2px solid #7CF7FF; outline-offset:2px; }
"""

HTML = '<div class="ce"></div>'

JS = r"""
const W = 600, H = 230, PL = 54, PR = 14, PT = 14, PB = 34;
const IW = W - PL - PR, IH = H - PT - PB;


function clamp(v, a, b) { return Math.max(a, Math.min(b, v)); }
function interp(pts, x) {
  if (x <= pts[0][0]) return pts[0][1];
  for (let i = 1; i < pts.length; i++) {
    if (x <= pts[i][0]) { const [x0, y0] = pts[i-1], [x1, y1] = pts[i]; return y0 + (y1 - y0) * (x - x0) / (x1 - x0); }
  }
  return pts[pts.length - 1][1];
}
function toPx(p) { return [PL + p[0] * IW, PT + (1 - p[1]) * IH]; }
function round4(v) { return Math.round(v * 10000) / 10000; }
function same(a, b) { return JSON.stringify(a) === JSON.stringify(b); }

export default function (component) {
  const { data, setStateValue, parentElement } = component;
  const root = parentElement.querySelector('.ce');
  // 편집 상태(곡선·편집 방식·실행 취소 기록)는 페이지에 하나만 두고, Streamlit 이 요소를 새로 만들어도 이어 쓴다
  let st = window.__plCurveEditor;
  if (!st) {
    st = { curve: data.curve, mode: 'draw', undo: [], drawing: null, drag: null, root: null };
    window.__plCurveEditor = st;
  }
  st.setStateValue = setStateValue;
  st.data = data;
  if (st.root !== root) { st.root = root; st.drawing = null; st.drag = null; build(root, st); }
  // Python 쪽 곡선이 바뀌었으면(작업 파일 불러오기, 버전 불러오기 등) 따라간다. 드래그 중에는 건드리지 않는다.
  if (!st.drawing && !st.drag && !same(st.sentCurve || null, data.curve) && !same(st.curve, data.curve)) {
    st.curve = data.curve;
  }
  render(root, st);
}

function commit(st, next) {
  st.undo.push(st.curve); if (st.undo.length > 40) st.undo.shift();
  st.curve = next.map(p => [round4(p[0]), round4(clamp(p[1], 0, 1))]);
  st.sentCurve = st.curve;
  st.setStateValue('curve', st.curve);
}

function build(root, st) {
  const presetOpts = Object.entries(st.data.presets).map(([k, v]) => `<option value="${k}">${v.label}</option>`).join('');
  root.innerHTML = `
    <div class="ce-bar">
      <div class="ce-tabs" role="tablist" aria-label="편집 방식">
        <button data-m="draw" role="tab">직접 그리기</button><button data-m="pts" role="tab">점으로 다듬기</button>
      </div>
      <span class="ce-sp"></span>
      <button class="ce-btn ce-undo" title="직전 편집으로 되돌리기">↶ 실행 취소</button>
      <button class="ce-btn ce-reset" title="처음 곡선으로 되돌리기">초기화</button>
    </div>
    <div class="ce-wrap"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="나만의 흐름 편집 영역"></svg></div>
    <div class="ce-bar" style="margin-top:8px">
      <select class="ce-preset" aria-label="기존 흐름 고르기">${presetOpts}</select>
      <button class="ce-btn ce-load">기존 흐름에서 시작</button>
    </div>
    <p class="ce-help"></p>`;
  root.querySelectorAll('.ce-tabs button').forEach(b => b.onclick = () => { st.mode = b.dataset.m; render(root, st); });
  root.querySelector('.ce-undo').onclick = () => {
    if (!st.undo.length) return;
    st.curve = st.undo.pop(); st.sentCurve = st.curve; st.setStateValue('curve', st.curve); render(root, st);
  };
  root.querySelector('.ce-reset').onclick = () => { commit(st, st.data.default); render(root, st); };
  root.querySelector('.ce-load').onclick = () => {
    const k = root.querySelector('.ce-preset').value; const ys = st.data.presets[k].ys;
    commit(st, ys.map((y, i) => [i / (ys.length - 1), y])); render(root, st);
  };
  const svg = root.querySelector('svg');
  const pos = (ev) => {
    const r = svg.getBoundingClientRect();
    const x = (ev.clientX - r.left) * W / r.width, y = (ev.clientY - r.top) * H / r.height;
    return [clamp((x - PL) / IW, 0, 1), clamp(1 - (y - PT) / IH, 0, 1)];
  };
  svg.addEventListener('pointerdown', (ev) => {
    ev.preventDefault();
    svg.setPointerCapture(ev.pointerId);
    const p = pos(ev);
    if (st.mode === 'pts') {
      // 가장 가까운 조절점을 잡는다 (가로 위치는 고정, 세로만 움직임)
      let best = 0, bd = 1e9;
      st.curve.forEach((q, i) => { const d = Math.abs(q[0] - p[0]); if (d < bd) { bd = d; best = i; } });
      st.drag = { i: best, start: st.curve.map(q => q.slice()) };
      st.curve = st.curve.map((q, i) => i === best ? [q[0], p[1]] : q);
    } else {
      st.drawing = { start: st.curve.map(q => q.slice()), path: [p] };
    }
    render(root, st);
  });
  svg.addEventListener('pointermove', (ev) => {
    if (!st.drag && !st.drawing) return;
    ev.preventDefault();
    const p = pos(ev);
    if (st.drag) { st.curve = st.curve.map((q, i) => i === st.drag.i ? [q[0], p[1]] : q); }
    else { st.drawing.path.push(p); st.curve = merged(st.drawing.start, st.drawing.path); }
    render(root, st);
  });
  const end = (ev) => {
    if (st.drag) {
      const start = st.drag.start, cur = st.curve; st.drag = null;
      if (!same(start, cur)) { st.curve = start; commit(st, cur); }
    } else if (st.drawing) {
      const start = st.drawing.start, path = st.drawing.path; st.drawing = null;
      const next = merged(start, path);
      if (!same(start, next)) { st.curve = start; commit(st, next); } else { st.curve = start; }
    }
    render(root, st);
  };
  svg.addEventListener('pointerup', end); svg.addEventListener('pointercancel', end);
}

// 그린 경로를 가로 위치별로 정리해 하나의 곡선으로: 그린 구간은 그 값, 나머지는 원래 곡선 값 (가로 13칸 격자)
function merged(start, path) {
  const G = %(grid)d;
  const xs = path.map(p => p[0]); const lo = Math.min(...xs), hi = Math.max(...xs);
  const byX = path.slice().sort((a, b) => a[0] - b[0]);
  const out = [];
  for (let i = 0; i < G; i++) {
    const x = i / (G - 1);
    let y;
    if (hi - lo < 1e-3) y = (Math.abs(x - lo) <= 0.5 / (G - 1)) ? byX[0][1] : interp(start, x);
    else if (x >= lo && x <= hi) {
      // 같은 가로 위치를 여러 번 지나가면 마지막으로 그린 값을 쓴다
      let found = null;
      for (let k = path.length - 1; k > 0; k--) {
        const a = path[k-1], b = path[k];
        const x0 = Math.min(a[0], b[0]), x1 = Math.max(a[0], b[0]);
        if (x >= x0 && x <= x1) { found = (x1 - x0 < 1e-6) ? b[1] : a[1] + (b[1] - a[1]) * (x - a[0]) / (b[0] - a[0]); break; }
      }
      y = found === null ? interp(byX, x) : found;
    } else y = interp(start, x);
    out.push([x, clamp(y, 0, 1)]);
  }
  return out;
}

function render(root, st) {
  const svg = root.querySelector('svg');
  root.querySelectorAll('.ce-tabs button').forEach(b => { const on = b.dataset.m === st.mode; b.classList.toggle('on', on); b.setAttribute('aria-selected', on); });
  root.querySelector('.ce-undo').disabled = !st.undo.length;
  svg.classList.toggle('pts', st.mode === 'pts');
  const n = Math.max(0, st.data.n || 0);
  const pts = st.curve.map(toPx);
  const line = pts.map((p, i) => (i ? 'L' : 'M') + p[0].toFixed(1) + ',' + p[1].toFixed(1)).join(' ');
  const area = line + ` L${PL + IW},${PT + IH} L${PL},${PT + IH} Z`;
  let grid = '';
  for (let k = 0; k <= 4; k++) { const y = PT + IH * k / 4; grid += `<line x1="${PL}" y1="${y}" x2="${PL + IW}" y2="${y}" stroke="rgba(255,255,255,${k % 4 ? .06 : .14})"/>`; }
  let applied = '';
  if (st.data.applied && !same(st.data.applied, st.curve)) {
    const ap = st.data.applied.map(toPx).map((p, i) => (i ? 'L' : 'M') + p[0].toFixed(1) + ',' + p[1].toFixed(1)).join(' ');
    applied = `<path d="${ap}" fill="none" stroke="#FFC46B" stroke-width="1.6" stroke-dasharray="5 4" opacity=".85"/>`;
  }
  let marks = '';
  if (n >= 1) {
    for (let i = 0; i < n; i++) {
      const x = n === 1 ? 0.5 : i / (n - 1); const [px, py] = toPx([x, interp(st.curve, x)]);
      marks += `<circle cx="${px}" cy="${py}" r="3.2" fill="#07080C" stroke="#EEF0F5" stroke-width="1.4"/>`;
      if (n <= 20) marks += `<text x="${px}" y="${PT + IH + 14}" fill="#8E94A6" font-size="10" text-anchor="middle">${i + 1}</text>`;
    }
  }
  let handles = '';
  if (st.mode === 'pts') {
    st.curve.forEach((q, i) => { const [px, py] = toPx(q);
      handles += `<circle class="handle" cx="${px}" cy="${py}" r="${st.drag && st.drag.i === i ? 9 : 7}" fill="#A98BFF" stroke="#EEF0F5" stroke-width="2"/>`; });
  }
  svg.innerHTML = `
    <defs><linearGradient id="ceg" x1="0" x2="1"><stop offset="0" stop-color="#7CF7FF"/><stop offset=".55" stop-color="#A98BFF"/><stop offset="1" stop-color="#FF7AD9"/></linearGradient>
      <linearGradient id="cef" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#A98BFF" stop-opacity=".28"/><stop offset="1" stop-color="#7CF7FF" stop-opacity=".02"/></linearGradient></defs>
    ${grid}
    <text x="${PL - 8}" y="${PT + 10}" fill="#8E94A6" font-size="11" text-anchor="end">신나게</text>
    <text x="${PL - 8}" y="${PT + IH}" fill="#8E94A6" font-size="11" text-anchor="end">차분하게</text>
    <text x="${PL}" y="${H - 4}" fill="#8E94A6" font-size="11">처음</text>
    <text x="${PL + IW}" y="${H - 4}" fill="#8E94A6" font-size="11" text-anchor="end">마지막 (곡 순서)</text>
    <path d="${area}" fill="url(#cef)"/>
    ${applied}
    <path d="${line}" fill="none" stroke="url(#ceg)" stroke-width="3.2" stroke-linejoin="round" stroke-linecap="round"/>
    ${marks}${handles}`;
  const help = st.mode === 'pts'
    ? '보라색 점을 위아래로 끌어 흐름을 다듬어요. 흰 점은 곡이 놓일 자리예요.'
    : '누른 채 움직여 흐름을 그려요. 그린 구간만 바뀌고 나머지는 그대로예요. 흰 점은 곡이 놓일 자리예요.';
  root.querySelector('.ce-help').textContent = help + (applied ? ' 주황 점선은 마지막으로 정렬에 쓴 흐름이에요.' : '');
}
""".replace("%(grid)d", str(GRID))

_editor = None


def _component():
    global _editor
    if _editor is None:
        _editor = st.components.v2.component("playline_curve_editor", html=HTML, css=CSS, js=JS)
    return _editor


def curve_editor(curve, *, presets: dict, default, applied, n_tracks: int, key: str = "curve_editor"):
    """편집기를 그리고, 사용자가 마지막으로 보낸 곡선을 돌려준다(없으면 None)."""
    res = _component()(key=key, data={"curve": curve, "presets": presets, "default": default,
                                      "applied": applied, "n": n_tracks},
                       on_curve_change=lambda: None)
    try:
        return res.curve
    except AttributeError:
        try:
            return res.get("curve")
        except Exception:
            return None
