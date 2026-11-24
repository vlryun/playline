# [AI 보조 도구: Claude Code (Claude Opus 5.5), 작업: '플레이리스트 연속 재생 플레이어']
"""화면 아래에 고정되는 플레이리스트 플레이어.

Streamlit은 버튼을 누를 때마다 스크립트를 다시 실행한다. 그때마다 오디오 요소를 새로 만들면
음악이 끊기거나 처음부터 다시 나온다. 그래서 오디오와 플레이어 UI는 페이지(부모 문서)에 한 번만
만들어 두고, 다시 실행될 때마다 작은 컴포넌트가 '재생 목록'만 갱신한다.

동작 규칙
- 사용자가 재생을 누르기 전에는 소리가 나지 않는다(자동 재생 없음).
- 오디오 요소는 하나뿐이라 두 곡이 동시에 나오지 않는다.
- 재생 중에 순서를 바꾸면 지금 곡은 계속 나오고, 바뀐 순서는 다음 곡부터 적용된다.
  지금 곡이 목록에서 빠지면 그 곡은 끝까지 재생되고, 다음은 바뀐 목록의 처음부터 이어진다.
- 재생할 수 없는 곡(음원 없음)은 목록·배열에서 지우지 않고 '건너뜀'으로 표시하며 다음 곡으로 넘어간다.
- 들을 순서는 '지금 순서 / 추천 순서 / 원래 순서' 중에서 고를 수 있다.
"""

from __future__ import annotations

import json


def media_url(sha: str, src: dict) -> str | None:
    """Streamlit 미디어 서버에 음원을 등록하고 주소를 받는다(스크립트가 실행될 때마다 다시 등록해야 유지됨)."""
    try:
        from streamlit import runtime
        if not runtime.exists():
            return None
        mgr = runtime.get_instance().media_file_mgr
        data = src["data"] if src.get("data") is not None else src.get("path")
        if data is None:
            return None
        return mgr.add(data, src.get("mime") or "audio/mpeg", f"playline.audio.{sha[:16]}")
    except Exception:
        return None


def queue_items(order: list[str], tracks: dict[str, dict], urls: dict[str, str], covers: dict[str, str | None]
                ) -> list[dict]:
    out = []
    for tid in order:
        t = tracks[tid]
        url = urls.get(t.get("sha256") or "")
        out.append({"id": tid, "title": t.get("title") or tid, "artist": t.get("artist") or "",
                    "cover": covers.get(tid) or "", "url": url or "", "playable": bool(url),
                    "dur": t.get("duration_sec") or 0})
    return out


PLAYER_JS = r"""
window.__plUpdate = function (DATA) {
  const P = window, D = document;
  if (!P.__pl) {
    const audio = D.createElement('audio');
    audio.preload = 'none'; audio.id = 'pl-audio'; audio.style.display = 'none';
    D.body.appendChild(audio);
    P.__pl = { audio, queues: {}, which: 'current', curId: null, lastNonce: 0, skipped: 0, msg: '' };
  }
  const S = P.__pl, A = S.audio;
  S.queues = DATA.queues; S.labels = DATA.labels;
  if (!S.queues[S.which]) S.which = 'current';

  function q() { return S.queues[S.which] || []; }
  function idxOf(id) { return q().findIndex(x => x.id === id); }
  function fmt(t) { if (!isFinite(t)) return '0:00'; t = Math.max(0, Math.floor(t)); return Math.floor(t / 60) + ':' + String(t % 60).padStart(2, '0'); }
  function esc(s) { const d = D.createElement('span'); d.textContent = s; return d.innerHTML; }

  let bar = D.getElementById('pl-player');
  if (!bar) {
    bar = D.createElement('div'); bar.id = 'pl-player'; bar.setAttribute('role', 'region'); bar.setAttribute('aria-label', '플레이리스트 플레이어');
    bar.innerHTML = `
      <div class="plp-art"><span class="plp-img"></span><span class="plp-eq"><i></i><i></i><i></i><i></i></span></div>
      <div class="plp-meta"><div class="plp-title">재생할 곡을 골라 주세요</div><div class="plp-sub"></div></div>
      <div class="plp-ctrl">
        <button class="plp-prev" aria-label="이전 곡" title="이전 곡">⏮</button>
        <button class="plp-play" aria-label="재생" title="재생/일시정지">▶</button>
        <button class="plp-next" aria-label="다음 곡" title="다음 곡">⏭</button>
      </div>
      <div class="plp-time"><span class="plp-cur">0:00</span><div class="plp-prog"><i></i></div><span class="plp-dur">0:00</span></div>
      <select class="plp-which" aria-label="들을 순서"></select>
      <div class="plp-note"></div>`;
    D.body.appendChild(bar);
    bar.querySelector('.plp-play').onclick = () => { if (!S.curId) { startFrom(0); } else if (A.paused) { A.play().catch(blocked); } else { A.pause(); } };
    bar.querySelector('.plp-next').onclick = () => step(1, true);
    bar.querySelector('.plp-prev').onclick = () => { if (A.currentTime > 3) { A.currentTime = 0; } else { step(-1, true); } };
    bar.querySelector('.plp-prog').onclick = (e) => { const r = e.currentTarget.getBoundingClientRect(); if (A.duration) A.currentTime = A.duration * (e.clientX - r.left) / r.width; };
    bar.querySelector('.plp-which').onchange = (e) => { S.which = e.target.value; render(); };
    A.addEventListener('ended', () => step(1, false));
    A.addEventListener('play', render); A.addEventListener('pause', render);
    A.addEventListener('timeupdate', tick); A.addEventListener('loadedmetadata', tick);
    A.addEventListener('error', () => { S.msg = '이 곡을 불러오지 못해 다음 곡으로 넘어가요.'; step(1, false); });
    setInterval(highlight, 800);
  }

  function blocked() { S.msg = '브라우저가 자동 재생을 막았어요. ▶ 버튼을 눌러 주세요.'; render(); }
  function load(item) {
    S.curId = item.id; S.curItem = item; S.msg = '';
    if (A.dataset.src !== item.url) { A.src = item.url; A.dataset.src = item.url; }
    A.play().catch(blocked); render();
  }
  function startFrom(i) {
    const list = q();
    for (let k = i; k < list.length; k++) { if (list[k].playable) { S.skipped += (k - i); return load(list[k]); } }
    S.msg = list.length ? '재생할 수 있는 곡이 없어요. (음원이 있는 곡만 들을 수 있어요)' : ''; render();
  }
  function step(dir, manual) {
    const list = q(); let i = idxOf(S.curId);
    if (i < 0) { i = dir > 0 ? -1 : list.length; }
    let skipped = 0;
    for (let k = i + dir; k >= 0 && k < list.length; k += dir) {
      if (list[k].playable) { if (skipped) S.msg = '재생할 수 없는 곡 ' + skipped + '곡을 건너뛰었어요 (목록에는 그대로 있어요).'; const m = S.msg; load(list[k]); S.msg = m; render(); return; }
      skipped++;
    }
    if (!manual) { A.pause(); S.msg = '플레이리스트 끝까지 들었어요.'; }
    render();
  }
  function tick() {
    bar.querySelector('.plp-cur').textContent = fmt(A.currentTime);
    bar.querySelector('.plp-dur').textContent = fmt(A.duration);
    bar.querySelector('.plp-prog i').style.width = (A.duration ? 100 * A.currentTime / A.duration : 0) + '%';
  }
  function cur() { if (!S.curId) return null; for (const k in S.queues) { const f = S.queues[k].find(x => x.id === S.curId); if (f) return f; } return S.curItem || null; }
  function highlight() {
    D.querySelectorAll('.pl-track').forEach(el => el.classList.toggle('pl-playing', !!S.curId && el.dataset.tid === S.curId && !A.paused));
  }
  function render() {
    const list = q(), c = cur(), playable = list.filter(x => x.playable).length;
    bar.classList.toggle('on', !!S.curId && !A.paused);
    bar.classList.toggle('empty', list.length === 0);
    bar.querySelector('.plp-play').textContent = (!A.paused && S.curId) ? '⏸' : '▶';
    bar.querySelector('.plp-play').setAttribute('aria-label', (!A.paused && S.curId) ? '일시정지' : '재생');
    bar.querySelector('.plp-title').textContent = c ? c.title : (playable ? '▶을 누르면 처음 곡부터 들어요' : '들을 수 있는 곡이 없어요');
    const pos = c ? (idxOf(c.id) + 1) : 0;
    bar.querySelector('.plp-sub').innerHTML = (c && c.artist ? esc(c.artist) + ' · ' : '') +
      (pos ? pos + '/' + list.length + '번째 · ' : '') + '들을 수 있는 곡 ' + playable + '/' + list.length;
    const img = bar.querySelector('.plp-img'); img.style.backgroundImage = c && c.cover ? 'url("' + c.cover + '")' : '';
    const sel = bar.querySelector('.plp-which');
    sel.innerHTML = Object.keys(S.queues).filter(k => (S.queues[k] || []).length).map(k => '<option value="' + k + '"' + (k === S.which ? ' selected' : '') + '>' + esc(S.labels[k]) + '</option>').join('');
    let note = S.msg;
    if (!note && playable < list.length) note = '재생할 수 없는 곡 ' + (list.length - playable) + '곡은 건너뛰고 들려줘요 (목록·배열에는 그대로 있어요).';
    bar.querySelector('.plp-note').textContent = note;
    tick(); highlight();
  }

  // 서버에서 온 '이 곡 재생' 명령은 한 번만 실행 (다시 실행돼도 반복하지 않음)
  const cmd = DATA.cmd;
  if (cmd && cmd.nonce > S.lastNonce) {
    S.lastNonce = cmd.nonce;
    let item = q().find(x => x.id === cmd.id);
    if (!item) { S.which = 'current'; item = q().find(x => x.id === cmd.id); }
    if (item && item.playable) load(item); else { S.msg = '이 곡은 음원이 없어 들을 수 없어요.'; }
  }
  if (!Object.values(S.queues).some(x => (x || []).length)) { A.pause(); S.curId = null; S.curItem = null; S.msg = ''; }
  render();
};
"""


def component_html(payload: dict) -> str:
    """페이지(부모 문서)에 플레이어 코드를 한 번만 심고, 매번 재생 목록만 넘긴다.

    컴포넌트 iframe은 Streamlit이 다시 실행될 때 새로 만들어지므로, 그 안에서 만든 이벤트 처리기는
    함께 사라진다. 그래서 플레이어 코드는 부모 문서의 <script>로 넣어 부모 쪽에서 계속 살아 있게 한다.
    """
    data = json.dumps(json.dumps(payload, ensure_ascii=False)).replace("</", "<\\/")
    code = json.dumps(PLAYER_JS).replace("</", "<\\/")
    return """<!doctype html><html><body><script>
(function () {
  const P = window.parent, D = P.document;
  if (!P.__plUpdate) {
    const s = D.createElement('script'); s.id = 'pl-player-js'; s.textContent = %s; D.head.appendChild(s);
  }
  if (P.__plUpdate) P.__plUpdate(JSON.parse(%s));
})();
</script></body></html>""" % (code, data)
