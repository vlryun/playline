# [AI 보조 도구: Claude Code (Claude Opus 5.5),
# 작업: '기존 음원 분석 코드를 바탕으로 PLAYLINE Streamlit 웹앱 화면 구현']
"""PLAYLINE — Your tracks. Your flow.

실행:  streamlit run app.py
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from playline import analysis, arrange as ar, library, storage, ui
from playline.demo import demo_track, load_demo

st.set_page_config(page_title="PLAYLINE · 플레이라인", page_icon="〰", layout="wide",
                   initial_sidebar_state="collapsed")

MIME = {".mp3": "audio/mpeg", ".wav": "audio/wav"}
DEFAULTS = {
    "ws": None,                 # 현재 작업 공간 (곡 목록·순서·버전)
    "analysis_cache": {},       # sha256 -> TrackAnalysis (같은 음원 재분석 방지)
    "sha_by_file_id": {},       # 업로더 file_id -> sha256 (매 실행마다 해시를 다시 계산하지 않기 위함)
    "analysis_runs": 0,         # 실제로 librosa 분석을 수행한 횟수 (검증용)
    "mode": "rise",
    "bpm_weight_pct": 50,
    "smooth": 0.2,
    "pin_first": "",            # "" = 고정 안 함 (None이면 selectbox가 '선택 없음'으로 표시됨)
    "pin_last": "",
    "uploader_key": 0,
    "json_key": 0,
    "focus_upload": False,
    "preview_id": None,
    "flash": [],
    "ws_seq": 0,
}
for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v if not isinstance(v, (dict, list)) else type(v)()

S = st.session_state


@st.cache_data(show_spinner=False)
def library_entries() -> list[dict]:
    return library.load_library()


LIB = library_entries()
LIB_AUDIO = library.audio_files(LIB)   # 서버에 음원 파일이 있는 라이브러리 곡 (sha256 -> 정보)


# ───────────────────────── 상태 도우미 ─────────────────────────

def flash(kind: str, msg: str):
    S.flash.append((kind, msg))


def settings() -> dict:
    return {"mode": S.mode, "bpm_weight": S.bpm_weight_pct / 100, "smooth": float(S.smooth),
            "pin_first": S.pin_first or None, "pin_last": S.pin_last or None}


def set_settings(s: dict):
    S.mode = s["mode"]
    S.bpm_weight_pct = int(round(s["bpm_weight"] * 100))
    S.smooth = float(s["smooth"])
    S.pin_first = s.get("pin_first") or ""
    S.pin_last = s.get("pin_last") or ""


def new_ws(kind: str, tracks: list[dict], excluded=None, versions=None, from_json=False) -> dict:
    S.ws_seq += 1
    ids = [t["id"] for t in tracks]
    return {"kind": kind, "tracks": {t["id"]: t for t in tracks}, "original": ids, "suggested": None,
            "suggested_key": None, "current": list(ids), "versions": versions or [],
            "excluded": excluded or [], "from_json": from_json, "seq": S.ws_seq}


def reset_pins_if_missing():
    ids = set(S.ws["tracks"]) if S.ws else set()
    if S.pin_first not in ids:
        S.pin_first = ""
    if S.pin_last not in ids:
        S.pin_last = ""


def score_inputs(ws) -> list[dict]:
    return [{"id": t, "bpm": storage.effective_bpm(ws["tracks"][t]), "rms": ws["tracks"][t]["rms"]}
            for t in ws["original"]]


def suggestion_key(ws) -> tuple:
    s = settings()
    factors = tuple(ws["tracks"][t].get("bpm_factor", 1.0) for t in ws["original"])
    return (s["mode"], s["bpm_weight"], s["smooth"], s["pin_first"], s["pin_last"], factors)


def locked_positions(ws) -> set[int]:
    cur = ws["current"]
    out = set()
    if S.pin_first and cur and cur[0] == S.pin_first:
        out.add(0)
    if S.pin_last and cur and cur[-1] == S.pin_last:
        out.add(len(cur) - 1)
    return out


def uploaded_audio(files) -> dict[str, dict]:
    """업로더 파일들을 sha256 기준으로 정리한다(업로드 순서 유지)."""
    out: dict[str, dict] = {}
    for f in files or []:
        sha = S.sha_by_file_id.get(f.file_id)
        data = f.getvalue()
        if sha is None:
            sha = analysis.file_sha256(data)
            S.sha_by_file_id[f.file_id] = sha
        if sha not in out:
            ext = "." + f.name.rsplit(".", 1)[-1].lower() if "." in f.name else ""
            out[sha] = {"filename": f.name, "data": data, "mime": MIME.get(ext, "audio/mpeg"), "size": len(data)}
    return out


# ───────────────────────── 동작 (콜백) ─────────────────────────

def start_demo():
    meta, tracks = load_demo()
    S.ws = new_ws("demo", tracks)
    S.demo_meta = meta
    reset_pins_if_missing()
    S.preview_id = None
    S.focus_upload = False
    run_arrange(silent=True)
    flash("info", "체험 모드를 시작했어요. 곡 제목은 실제 차트에서 가져왔지만 빠르기·소리 크기는 예시 값이에요.")


def start_library():
    picked = [e for e in LIB if S.get(f"lib_pick_{e['sha256'][:12]}")]
    if not picked:
        flash("warning", "라이브러리에서 곡을 한 곡 이상 골라 주세요.")
        return
    prev = S.ws
    tracks = [library.to_track(e) for e in picked]
    keep = prev["versions"] if prev and prev["kind"] == "measured" and set(prev["tracks"]) == {t["id"] for t in tracks} else []
    S.ws = new_ws("measured", tracks, versions=keep)
    reset_pins_if_missing()
    S.preview_id = None
    S.focus_upload = False
    run_arrange(silent=True)
    flash("success", f"{len(tracks)}곡을 담았어요. 추천 순서를 만들어 뒀으니 아래에서 확인해 보세요.")


def set_library_picks(value: bool, shas: list[str]):
    for sha in shas:
        S[f"lib_pick_{sha[:12]}"] = value


def focus_upload():
    S.focus_upload = True


def run_analysis(files):
    audio = uploaded_audio(files)
    if not files:
        flash("warning", "먼저 MP3나 WAV 파일을 올려 주세요.")
        return
    prev = S.ws
    tracks, excluded, seen = [], [], {}
    titles: dict[str, int] = {}
    progress = st.progress(0.0, text="분석 준비 중…")
    for i, f in enumerate(files, start=1):
        sha = S.sha_by_file_id.get(f.file_id) or analysis.file_sha256(f.getvalue())
        if sha in seen:
            excluded.append({"filename": f.name, "status": "duplicate",
                             "message": f"'{seen[sha]}'과(와) 내용이 같은 파일이라 한 번만 넣었습니다."})
            progress.progress(i / len(files), text=f"{i}/{len(files)} · 중복 건너뜀: {f.name}")
            continue
        seen[sha] = f.name
        cached = S.analysis_cache.get(sha)
        if cached is not None:
            res = cached
            progress.progress(i / len(files), text=f"{i}/{len(files)} · 이전 분석 결과 사용: {f.name}")
        else:
            progress.progress((i - 1) / len(files), text=f"{i}/{len(files)} · 분석 중: {f.name}")
            res = analysis.analyze_bytes(f.getvalue(), f.name)
            S.analysis_runs += 1
            if res.status != "error":  # 오류는 다시 시도할 수 있도록 캐시하지 않음
                S.analysis_cache[sha] = res
            progress.progress(i / len(files), text=f"{i}/{len(files)} · 완료: {f.name}")
        if not res.usable:
            excluded.append({"filename": f.name, "status": res.status, "message": res.message})
            continue
        title = analysis.title_from_filename(f.name)
        titles[title] = titles.get(title, 0) + 1
        if titles[title] > 1:
            title = f"{title} ({titles[title]})"
        tracks.append({
            "id": sha[:12], "title": title, "artist": None, "filename": f.name, "sha256": sha,
            "size_bytes": res.size_bytes, "duration_sec": res.duration_sec, "bpm_raw": res.bpm,
            "bpm_factor": 1.0, "rms": res.rms_mean, "status": res.status, "category": None,
            "bpm_alternatives": res.bpm_alternatives, "message": res.message,
        })
    progress.empty()

    if not tracks:
        flash("error", "분석할 수 있는 곡이 없어요. 아래 '넣지 못한 파일'에서 이유를 확인해 주세요.")
        S.ws = new_ws("measured", [], excluded=excluded)
        return

    # 같은 곡 구성이면 BPM 해석·순서·버전을 유지하고, 바뀌었으면 순서를 새로 시작한다
    if prev and prev["kind"] == "measured" and set(prev["tracks"]) == {t["id"] for t in tracks}:
        for t in tracks:
            t["bpm_factor"] = prev["tracks"][t["id"]].get("bpm_factor", 1.0)
        ws = new_ws("measured", tracks, excluded=excluded, versions=prev["versions"])
        ws["current"] = [t for t in prev["current"]]
        ws["suggested"], ws["suggested_key"] = prev["suggested"], prev["suggested_key"]
        S.ws = ws
        flash("success", f"{len(tracks)}곡을 다시 불러왔어요. 곡 목록이 같아서 지금 순서와 저장한 순서는 그대로 뒀어요.")
    else:
        if prev and prev["kind"] == "demo":
            flash("info", "체험용 예시 곡을 비우고 올린 곡으로 바꿨어요.")
        keep = [v for v in (prev or {}).get("versions", [])] if prev and prev["kind"] == "measured" else []
        S.ws = new_ws("measured", tracks, excluded=excluded, versions=keep)
        reset_pins_if_missing()
        run_arrange(silent=True)
        flash("success", f"{len(tracks)}곡을 분석했어요. 올린 순서를 '원래 순서'로 두고, 추천 순서도 만들어 뒀어요.")
    S.focus_upload = False


def run_arrange(silent=False):
    ws = S.ws
    if not ws or not ws["original"]:
        return
    scores = ar.compute_scores(score_inputs(ws), S.bpm_weight_pct / 100)
    res = ar.arrange(ws["original"], scores, S.mode, S.pin_first or None, S.pin_last or None, float(S.smooth))
    if res.error:
        flash("error", res.error)
        return
    ws["suggested"] = res.order
    ws["suggested_key"] = suggestion_key(ws)
    ws["current"] = list(res.order)
    for n in res.notes or []:
        flash("info", n)
    if not silent:
        flash("success", f"'{ar.MODES[S.mode]['label']}' 흐름으로 순서를 추천했어요. 화살표로 직접 바꿀 수도 있어요.")


def choose_mode(mode):
    S.mode = mode


def on_pin_change():
    if S.ws and S.pin_first and S.pin_first == S.pin_last:
        return  # 화면에서 오류 안내, 순서는 바꾸지 않음
    if S.ws:
        S.ws["current"] = ar.apply_pins(S.ws["current"], S.pin_first or None, S.pin_last or None)


def move_track(index, delta):
    ws = S.ws
    ws["current"] = ar.move(ws["current"], index, delta, locked_positions(ws))


def restore(which):
    ws = S.ws
    base = ws["suggested"] if which == "suggested" else ws["original"]
    if base:
        ws["current"] = ar.apply_pins(list(base), S.pin_first or None, S.pin_last or None) \
            if not (S.pin_first and S.pin_first == S.pin_last) else list(base)


def save_version(name):
    ws = S.ws
    name = (name or "").strip() or f"버전 {len(ws['versions']) + 1}"
    if any(v["name"] == name for v in ws["versions"]):
        flash("warning", f"'{name}' 이름의 버전이 이미 있습니다. 다른 이름을 써 주세요.")
        return
    ws["versions"].append({"name": name, "created_at": datetime.now().isoformat(timespec="seconds"),
                           "order": list(ws["current"]), "settings": settings()})
    S.version_name = ""
    flash("success", f"현재 순서를 '{name}'(으)로 이 세션에 저장했습니다. 브라우저를 닫으면 사라지니 필요하면 JSON으로 내려받으세요.")


def load_version(i):
    ws = S.ws
    v = ws["versions"][i]
    if set(v["order"]) != set(ws["tracks"]):
        flash("error", "이 버전의 곡 구성이 현재 목록과 달라 불러올 수 없습니다.")
        return
    set_settings(v["settings"])
    reset_pins_if_missing()
    ws["current"] = list(v["order"])
    flash("success", f"'{v['name']}' 버전의 순서와 설정을 불러왔습니다.")


def delete_version(i):
    v = S.ws["versions"].pop(i)
    flash("info", f"'{v['name']}' 버전을 지웠습니다.")


def import_project(project):
    tracks = list(project["tracks"].values())
    for t in tracks:
        t["is_demo"] = project["data_kind"] == "demo"
    ws = new_ws(project["data_kind"], [project["tracks"][t] for t in project["original"]],
                versions=project["versions"], from_json=True)
    ws["current"] = project["current"]
    ws["suggested"] = project["suggested"]
    S.ws = ws
    set_settings(project["settings"])
    reset_pins_if_missing()
    ws["suggested_key"] = suggestion_key(ws) if project["suggested"] else None
    S.json_key += 1
    flash("success", "JSON에서 곡 정보·순서·설정·버전을 불러왔습니다. 음원은 포함되어 있지 않습니다.")


def apply_demo_edit(df: pd.DataFrame):
    tracks, errs = [], []
    for i, row in enumerate(df.to_dict("records"), start=1):
        title = str(row.get("곡명") or "").strip()
        if not title:
            continue
        try:
            rms = float(row.get("RMS(가상)"))
            if not rms > 0:
                raise ValueError
        except (TypeError, ValueError):
            errs.append(f"{i}번째 줄 '{title}': RMS(가상)는 0보다 큰 숫자여야 합니다.")
            continue
        bpm = row.get("BPM(가상)")
        try:
            bpm = None if bpm is None or pd.isna(bpm) else float(bpm)
        except (TypeError, ValueError):
            bpm = None
        tracks.append(demo_track(tid=f"demo-{i:02d}", title=title, artist=row.get("아티스트") or None,
                                 category=row.get("분류") or None, chart=None, bpm=bpm, rms=rms))
    if errs:
        for e in errs:
            flash("error", e)
        return
    if not tracks:
        flash("error", "곡이 한 곡 이상 있어야 합니다.")
        return
    S.ws = new_ws("demo", tracks)
    reset_pins_if_missing()
    run_arrange(silent=True)
    flash("success", f"데모 목록을 {len(tracks)}곡으로 바꿨습니다(이 세션에만 적용).")


# ───────────────────────── 화면 ─────────────────────────

st.html(ui.css())
st.html(ui.icon_css())

hero_l, hero_r = st.columns([3, 1.25], vertical_alignment="bottom")
with hero_l:
    st.html(ui.hero_html())
with hero_r:
    with st.container(horizontal=True, horizontal_alignment="right", gap="small"):
        st.button("내 음악 올리기", type="primary", icon=":material/upload:", on_click=focus_upload, key="hero_upload")
        st.button("데모 체험", icon=":material/play_circle:", on_click=start_demo, key="hero_demo")

for kind, msg in S.flash:
    getattr(st, kind)(msg)
S.flash = []

left, main = st.columns([1.15, 2.5], gap="large")

# ─────────── 왼쪽: 설정 영역 ───────────
with left:
    with st.container(key="panel"):
        with st.container(key="focus_upload" if S.focus_upload else "upload_box"):
            st.html(ui.step_html(1, "곡 넣기"))
            tab_lib, tab_up = st.tabs(["라이브러리", "파일 올리기"])
        with tab_lib:
            if not LIB:
                st.caption("라이브러리가 비어 있습니다. tools/build_library.py 로 곡을 추가하세요.")
            q = st.text_input("곡 검색", key="lib_query", placeholder="곡 제목·가수 검색", label_visibility="collapsed")
            shown = library.search(LIB, q)
            with st.container(key="lib_list", height=260 if len(shown) > 6 else "content"):
                for e in shown:
                    bpm = "—" if e.get("bpm") is None else f"{e['bpm']:.1f}"
                    who = f" · {e['artist']}" if e.get("artist") else ""
                    play = "" if e["sha256"] in LIB_AUDIO else " · 듣기 불가"
                    dur = ui.fmt_duration(e.get("duration_sec"))
                    st.checkbox(f"**{e['title']}**{who}  \n:gray[빠르기 {bpm} · {dur}{play}]",
                                key=f"lib_pick_{e['sha256'][:12]}")
            if q and not shown:
                st.caption("검색 결과가 없습니다.")
            n_pick = sum(1 for e in LIB if S.get(f"lib_pick_{e['sha256'][:12]}"))
            l1, l2 = st.columns(2)
            l1.button("전체", width="stretch", on_click=set_library_picks, args=(True, [e["sha256"] for e in shown]),
                      disabled=not shown, key="lib_all")
            l2.button("해제", width="stretch", on_click=set_library_picks, args=(False, [e["sha256"] for e in LIB]),
                      disabled=not n_pick, key="lib_none")
            st.button(f"{n_pick}곡으로 시작", type="primary", width="stretch", icon=":material/queue_music:",
                      on_click=start_library, disabled=not n_pick, key="lib_start")
            st.html('<p class="pl-help">곡을 고르면 미리 측정해 둔 빠르기·소리 크기로 바로 순서를 추천해요. '
                    '저작권 때문에 “듣기 불가” 곡은 이 사이트에서 재생되지 않아요.</p>')
        with tab_up:
            files = st.file_uploader(
                "MP3·WAV 파일 (여러 개 가능)", type=["mp3", "wav"], accept_multiple_files=True,
                key=f"uploader_{S.uploader_key}",
                help=f"파일당 최대 {analysis.MAX_FILE_MB}MB. 올린 곡은 이 앱 안에서만 분석하고 외부 AI 서비스로 보내지 않아요. 분석이 끝나면 임시 파일은 바로 지워요.")
            st.html(f'<p class="pl-help">파일당 최대 {analysis.MAX_FILE_MB}MB · 올린 순서가 “원래 순서”가 돼요 · '
                    f'곡마다 분석에 몇 초~수십 초 걸려요.</p>')
            audio_store = {**LIB_AUDIO, **uploaded_audio(files)}
            c1, c2 = st.columns(2)
            analyze_clicked = c1.button("분석 시작", type="primary", width="stretch", disabled=not files,
                                        icon=":material/graphic_eq:")
            c2.button("데모 체험", width="stretch", on_click=start_demo, key="panel_demo")
        if analyze_clicked:
            run_analysis(files)
            st.rerun()

        ws = S.ws
        if ws and ws["kind"] == "measured" and not ws["from_json"] and files:
            new_files = [v["filename"] for sha, v in audio_store.items()
                         if sha[:12] not in ws["tracks"] and not any(e["filename"] == v["filename"] for e in ws["excluded"])]
            removed = [t["title"] for t in ws["tracks"].values()
                       if t.get("source") != "library" and t["sha256"] not in audio_store]
            if new_files or removed:
                msg = "업로드 목록이 현재 작업과 다릅니다."
                if new_files:
                    msg += f" 새 파일 {len(new_files)}개."
                if removed:
                    msg += f" 목록에서 빠진 곡 {len(removed)}개."
                st.warning(msg + " '분석 시작'을 눌러야 반영돼요(이미 분석한 곡은 다시 분석하지 않아요).")

        st.divider()
        st.html(ui.step_html(2, "어떤 흐름으로 들을까요?"))
        for mode, info in ar.MODES.items():
            sel = S.mode == mode
            with st.container(key=f"modecard_{'sel_' if sel else ''}{mode}", horizontal=True,
                              vertical_alignment="center", gap="small", wrap=False):
                st.html(ui.mode_curve_html(mode, info["label"], sel), width="content")
                st.button(info["label"], key=f"mode_btn_{mode}", on_click=choose_mode, args=(mode,),
                          type="tertiary", width="stretch", help=info["desc"])
        st.html(f'<p class="pl-help pl-mode-desc">{ui.esc(ar.MODES[S.mode]["desc"])}</p>')

        st.divider()
        st.html(ui.step_html(3, "처음·마지막 곡 정하기 (선택)"))
        ws = S.ws
        ids = list(ws["original"]) if ws else []
        reset_pins_if_missing()
        title_of = (lambda t: "정하지 않음" if not t else ws["tracks"][t]["title"]) if ws else (lambda t: "정하지 않음")
        pc1, pc2 = st.columns(2)
        pc1.selectbox("처음 곡", [""] + ids, format_func=title_of, key="pin_first", on_change=on_pin_change,
                      disabled=not ws)
        pc2.selectbox("마지막 곡", [""] + ids, format_func=title_of, key="pin_last", on_change=on_pin_change,
                      disabled=not ws)
        pin_error = None
        if S.pin_first and S.pin_first == S.pin_last:
            pin_error = "같은 곡을 처음과 마지막에 동시에 둘 수는 없어요. 둘 중 하나를 바꿔 주세요."
            st.error(pin_error)
        elif ws and len(ids) == 1 and (S.pin_first or S.pin_last):
            st.caption("곡이 한 곡뿐이라 순서는 그대로예요.")
        st.html('<p class="pl-help">정한 곡은 추천할 때도, 직접 바꿀 때도 그 자리에 그대로 있어요. '
                '풀려면 \'정하지 않음\'을 고르세요.</p>')

        with st.expander("더 세밀하게 조절 (선택)", icon=":material/tune:"):
            st.slider("빠르기를 얼마나 중요하게 볼까요? (%)", 0, 100, key="bpm_weight_pct", step=5,
                      help="나머지는 소리 크기로 채워요. 50%면 빠르기와 소리 크기를 똑같이 봐요.")
            st.caption(f"빠르기 {S.bpm_weight_pct}% · 소리 크기 {100 - S.bpm_weight_pct}%")
            st.slider("곡 사이를 얼마나 부드럽게 이을까요?", 0.0, 1.0, key="smooth", step=0.05,
                      help="0이면 원하는 흐름 모양만 따라가요. 올릴수록 앞뒤 곡의 분위기 차이가 갑자기 커지는 순서를 피해요.")
            st.caption("잘 모르겠으면 그대로 두셔도 충분해요.")

        st.divider()
        stale = bool(ws and ws["suggested"] and ws["suggested_key"] != suggestion_key(ws))
        st.button("추천 순서 만들기", type="primary", width="stretch", icon=":material/auto_awesome:",
                  disabled=not ws or not ws["original"] or bool(pin_error), on_click=run_arrange,
                  key="arrange_btn")
        if stale:
            st.caption("설정이 바뀌었어요. 다시 누르면 새 설정으로 추천해요(지금 순서는 바뀌어요).")
        elif ws and ws["original"]:
            st.caption("같은 곡·같은 설정이면 언제나 같은 순서가 나와요. 무작위 셔플이 아니에요.")


def render_import_and_help():
    """JSON 불러오기와 지표 설명. 작업 공간이 비어 있어도 쓸 수 있다."""
    with st.expander("저장해 둔 작업 파일 열기", icon=":material/file_open:", expanded=not S.ws):
        st.caption("PLAYLINE에서 받은 작업 파일(JSON)을 올리면 곡 목록·순서·설정·저장한 순서를 되살려요. "
                   "음악 파일은 들어 있지 않아서, 들으려면 같은 음악 파일을 다시 올려 주세요. "
                   "파일 이름이 달라도 내용이 같은 파일이면 알아서 연결해요.")
        jf = st.file_uploader("작업 파일 (JSON)", type=["json"], key=f"json_{S.json_key}")
        if jf is not None:
            project, errs = storage.parse_project(jf.getvalue())
            if errs:
                st.error("열 수 없는 파일이에요.\n\n" + "\n".join(f"- {e}" for e in errs[:12]))
            else:
                m = storage.match_audio(project["tracks"], audio_store) if project["data_kind"] == "measured" else None
                kind_txt = "실제 측정값" if project["data_kind"] == "measured" else "체험용 예시 값"
                st.success(f"열 수 있어요 · {len(project['tracks'])}곡 · {kind_txt} · 저장한 순서 {len(project['versions'])}개")
                if m:
                    st.write(f"지금 올린 음악과 연결됨: {len(m['linked'])}곡 / 연결 안 됨 {len(m['missing'])}곡 / "
                             f"작업 파일에 없는 곡 {len(m['extra'])}개")
                    if m["missing"]:
                        st.warning("아직 연결 안 된 곡 (같은 파일을 올리면 연결돼요): " +
                                   ", ".join(project["tracks"][t]["filename"] or t for t in m["missing"][:10]))
                    if m["extra"]:
                        st.info("작업 파일에 없는 곡은 이번 작업에 넣지 않아요: " +
                                ", ".join(audio_store[s]["filename"] for s in m["extra"][:10]))
                    for tid, newname in m["renamed"]:
                        st.caption(f"'{project['tracks'][tid]['filename']}' → 내용이 같은 '{newname}'과 연결했어요")
                # 설정 위젯 값을 바꿔야 하므로 위젯이 만들어지기 전에 실행되는 콜백으로 처리
                st.button("이 작업 이어서 하기", type="primary", key="import_btn",
                          on_click=import_project, args=(project,))

    with st.expander("용어가 궁금하다면", icon=":material/help:"):
        st.markdown("""
- **빠르기 (BPM)** — 1분에 박자가 몇 번 오는지예요. 숫자가 클수록 빠른 곡이에요. 컴퓨터가 잴 때 실제보다 절반이나 두 배로 잡힐 수 있어서, '곡별 상세 정보'에서 바로잡을 수 있어요.
- **소리 크기 (RMS)** — 곡 전체의 평균 소리 세기예요. 클수록 크고 꽉 찬 느낌으로 들려요. 슬픔·기쁨 같은 감정을 뜻하지는 않아요.
- **흐름 점수** — 빠르기와 소리 크기를 합쳐서 0(가장 잔잔)~1(가장 강함)로 나타낸 점수예요. 지금 고른 곡들끼리 비교한 값이라, 다른 플레이리스트의 점수와는 비교할 수 없어요.
- **원하는 흐름** — 고른 흐름(점점 신나게 / 점점 차분하게 / 올렸다가 내리기)을 선으로 그린 거예요. 그래프의 흰 점선이에요.
- **원하는 흐름과의 차이** — 각 자리의 흐름 점수가 원하는 흐름 선에서 평균적으로 얼마나 떨어져 있는지예요. 작을수록 잘 맞아요.
- **곡 넘어갈 때 변화** — 앞뒤 곡의 흐름 점수 차이예요. 작을수록 자연스럽게 이어져요.
- **추천은 어떻게 만들까?** — 흐름 점수가 낮은 곡부터 원하는 흐름의 낮은 자리에 차례로 맞춰 넣고, '곡 사이 부드럽게 잇기' 값만큼 앞뒤 곡 차이도 줄이도록 자리를 바꿔 봐요. 무작위가 아니라서 같은 곡·같은 설정이면 결과도 항상 같아요.
""")



# ─────────── 중앙: 작업 영역 ───────────
with main:
    ws = S.ws
    if not ws or not ws["original"]:
        st.html("""
<div class="pl-empty">
  <h3>어떤 곡으로 플레이리스트를 만들까요?</h3>
  <p class="pl-note">PLAYLINE은 곡마다 빠르기와 소리 크기를 재서, 원하는 분위기 흐름에 맞게 듣기 좋은 순서를 추천해 드려요.</p>
  <ol>
    <li><b>라이브러리</b> — 왼쪽에서 곡을 체크하고 'N곡으로 시작' (파일 올릴 필요 없음)</li>
    <li><b>내 음악</b> — '파일 올리기' 탭에 MP3·WAV를 올리고 '분석 시작'</li>
    <li><b>데모 체험</b> — 예시 곡 목록으로 사용법만 둘러보기 (듣기 불가)</li>
    <li>흐름을 고르고 '추천 순서 만들기' → 그래프로 비교 → 화살표로 직접 바꾸기 → 저장</li>
  </ol>
</div>""")
        if ws and ws["excluded"]:
            st.subheader("넣지 못한 파일")
            for e in ws["excluded"]:
                st.warning(f"**{e['filename']}** — {e['message']}")
        render_import_and_help()
        st.stop()

    tracks = ws["tracks"]
    demo = ws["kind"] == "demo"
    scores = ar.compute_scores(score_inputs(ws), S.bpm_weight_pct / 100)
    raw = {t: {"bpm": storage.effective_bpm(tracks[t]), "rms": tracks[t]["rms"], "score": scores[t].score}
           for t in ws["original"]}

    def has_audio(t):
        return bool(tracks[t].get("sha256")) and tracks[t]["sha256"] in audio_store

    # 상태 표시
    cur, sug, org = ws["current"], ws["suggested"], ws["original"]
    if sug and cur == sug:
        state = '<span class="pl-badge dot">추천 순서</span>'
    elif cur == org:
        state = '<span class="pl-badge dot">원래 순서</span>'
    else:
        diff = sum(1 for a, b in zip(cur, sug or org) if a != b)
        state = f'<span class="pl-badge edit dot">직접 바꾸는 중 · {"추천" if sug else "원래"} 순서와 {diff}곡 다름</span>'
    kind_badge = ('<span class="pl-badge demo dot">체험용 예시 값 (실제로 잰 값 아님)</span>' if demo
                  else '<span class="pl-badge real dot">실제 곡에서 잰 값</span>')
    linked = sum(1 for t in org if has_audio(t))
    extra = f'<span class="pl-badge">{len(org)}곡</span>'
    if not demo:
        extra += f'<span class="pl-badge">들을 수 있는 곡 {linked}/{len(org)}</span>'
    if ws["from_json"]:
        extra += '<span class="pl-badge">작업 파일에서 불러옴</span>'
    st.html(f'<div class="pl-badges">{kind_badge}{state}{extra}</div>')
    if demo:
        st.html('<div class="pl-demo-note"><b>체험 모드</b> — 곡 제목·가수는 2026-11-19 공개 차트에서 가져왔지만, '
                '빠르기·소리 크기는 사용법을 보여 주려고 <b>임의로 넣은 값</b>이에요(실제로 잰 값 아님). '
                '음악 파일이 없어 들을 수 없어요. 진짜 곡으로 해 보려면 왼쪽 라이브러리나 파일 올리기를 써 주세요.</div>')

    # ── 곡 목록 ──
    st.html(ui.section_html("플레이리스트"))
    b1, b2, b3 = st.columns([1, 1, 2.2])
    b1.button("추천 순서로 되돌리기", icon=":material/auto_awesome:", width="stretch", on_click=restore,
              args=("suggested",), disabled=not sug or cur == sug)
    b2.button("원래 순서로 되돌리기", icon=":material/history:", width="stretch", on_click=restore, args=("original",),
              disabled=cur == org)
    b3.caption("화살표로 곡을 위아래로 옮기면 아래 그래프가 바로 바뀌어요. "
               "흐름 점수는 이 목록 안에서 곡끼리 비교한 값이에요.")

    if S.preview_id in tracks and has_audio(S.preview_id):
        t = tracks[S.preview_id]
        a = audio_store[t["sha256"]]
        with st.container(border=True):
            st.markdown(f"**지금 듣는 곡** · {ui.esc(t['title'])}")
            st.audio(a["data"] if a["data"] is not None else a["path"], format=a["mime"], autoplay=False)

    locks = locked_positions(ws)
    orig_pos = {t: i for i, t in enumerate(org, start=1)}
    n = len(cur)
    for i, tid in enumerate(cur):
        t = tracks[tid]
        with st.container(key=f"trackrow_{i}", horizontal=True, vertical_alignment="center", gap="small",
                          wrap=False):
            st.html(ui.track_row_html(i + 1, t, raw[tid]["bpm"], raw[tid]["score"], demo=demo,
                                      locked=i in locks, orig_pos=orig_pos[tid], has_audio=has_audio(tid)),
                    width="stretch")
            playable = has_audio(tid)
            st.button("재생" if playable else "",
                      key=f"play_{tid}", icon=":material/play_arrow:" if playable else ":material/music_off:",
                      disabled=not playable, on_click=lambda x=tid: setattr(S, "preview_id", x),
                      help="위쪽 플레이어에 이 곡을 올려요(바로 재생되지는 않아요)" if playable else
                      ("체험 모드는 음악 파일이 없어 들을 수 없어요" if demo else
                       "저작권 때문에 이 사이트에서는 들을 수 없어요(측정값만 있어요)" if t.get("source") == "library"
                       else "같은 음악 파일을 다시 올리면 들을 수 있어요"),
                      width="content")
            up_ok = i > 0 and i not in locks and (i - 1) not in locks
            down_ok = i < n - 1 and i not in locks and (i + 1) not in locks
            st.button("", key=f"up_{tid}", icon=":material/arrow_upward:", on_click=move_track, args=(i, -1),
                      disabled=not up_ok, help="한 칸 위로")
            st.button("", key=f"down_{tid}", icon=":material/arrow_downward:", on_click=move_track, args=(i, 1),
                      disabled=not down_ok, help="한 칸 아래로")

    if ws["excluded"]:
        with st.expander(f"넣지 못한 파일 {len(ws['excluded'])}개", icon=":material/error:", expanded=True):
            for e in ws["excluded"]:
                st.markdown(f"- **{ui.esc(e['filename'])}** — {e['message']}")

    with st.expander("곡별 상세 정보 · 빠르기 바로잡기", icon=":material/table_rows:"):
        st.caption("빠르기(BPM)는 1분에 박자가 몇 번 오는지를 뜻해요. 컴퓨터가 잴 때 실제보다 절반이나 두 배로 "
                   "잡힐 때가 있어서, 들어 보고 이상하면 '빠르기 바로잡기'에서 고칠 수 있어요.")
        factor_label = {1.0: "그대로", 0.5: "절반으로 (½)", 2.0: "두 배로 (×2)"}
        label_factor = {v: k for k, v in factor_label.items()}
        rows = []
        for tid in org:
            t = tracks[tid]
            rows.append({"곡명": t["title"], "길이": ui.fmt_duration(t.get("duration_sec")),
                         "잰 빠르기": t.get("bpm_raw"), "빠르기 바로잡기": factor_label.get(t.get("bpm_factor", 1.0)),
                         "쓰는 빠르기": storage.effective_bpm(t), "소리 크기": t["rms"],
                         "상태": ("예시 값" if demo else ("빠르기 못 잼" if t.get("bpm_raw") is None else "측정 완료"))})
        edited = st.data_editor(
            pd.DataFrame(rows), key=f"bpm_editor_{ws['seq']}", hide_index=True, width="stretch",
            disabled=["곡명", "길이", "잰 빠르기", "쓰는 빠르기", "소리 크기", "상태"],
            column_config={
                "빠르기 바로잡기": st.column_config.SelectboxColumn(options=list(factor_label.values()), required=True),
                "잰 빠르기": st.column_config.NumberColumn(format="%.1f", help="1분당 박자 수(BPM)"),
                "쓰는 빠르기": st.column_config.NumberColumn(format="%.1f"),
                "소리 크기": st.column_config.NumberColumn(format="%.4f", help="곡 전체의 평균 소리 세기(RMS). 클수록 크게 들려요."),
            })
        changed = False
        for tid, lab in zip(org, edited["빠르기 바로잡기"]):
            f = label_factor.get(lab, 1.0)
            if tracks[tid]["bpm_raw"] is not None and tracks[tid].get("bpm_factor", 1.0) != f:
                tracks[tid]["bpm_factor"] = f
                changed = True
        if changed:
            st.rerun()

    if demo:
        with st.expander("체험용 곡 목록 바꾸기", icon=":material/edit_note:"):
            st.caption("체험용 곡 제목과 예시 값을 바꿀 수 있어요. 지금 창에서만 적용돼요.")
            df = pd.DataFrame([{"곡명": tracks[t]["title"], "아티스트": tracks[t].get("artist"),
                                "분류": tracks[t].get("category"), "BPM(가상)": tracks[t].get("bpm_raw"),
                                "RMS(가상)": tracks[t]["rms"]} for t in org])
            de = st.data_editor(df, num_rows="dynamic", key=f"demo_editor_{ws['seq']}", hide_index=True,
                                width="stretch")
            st.button("데모 목록 적용", key="apply_demo", on_click=apply_demo_edit, args=(de,))

    # ── 비교 그래프 ──
    st.html(ui.section_html("흐름 그래프로 비교하기"))
    g1, g2 = st.columns([1.4, 2])
    metric = g1.segmented_control("무엇을 볼까요?", ["흐름 점수", "빠르기", "소리 크기"], default="흐름 점수", key="metric",
                                  required=True)
    version_names = [v["name"] for v in ws["versions"] if set(v["order"]) == set(tracks)]
    overlay = g2.selectbox("저장한 순서도 같이 보기", ["없음"] + version_names, key="overlay") if version_names else "없음"

    series = {"원래 순서": org}
    if sug:
        series["추천 순서"] = sug
    if cur != sug:
        series["내가 바꾼 순서"] = cur
    if overlay != "없음":
        series[f"저장: {overlay}"] = next(v["order"] for v in ws["versions"] if v["name"] == overlay)

    lo, hi = ar.score_range(scores)
    if metric == "흐름 점수":
        values = {t: raw[t]["score"] for t in org}
        target = list(ar.target_curve(S.mode, len(org), lo, hi))
        domain = (-0.04, 1.04)
        label = "흐름 점수 (0 차분 ~ 1 신남)"
    elif metric == "빠르기":
        values = {t: raw[t]["bpm"] for t in org}
        target, label = None, "빠르기 (BPM, 1분당 박자 수)"
        domain = ui.padded_domain(list(values.values()))
    else:
        values = {t: raw[t]["rms"] for t in org}
        target, label = None, "소리 크기 (RMS)"
        domain = ui.padded_domain(list(values.values()))

    st.altair_chart(ui.flow_chart(series, tracks, values, label, domain, target, raw), theme=None,
                    width="stretch")
    notes = ["점 하나가 곡 하나예요. 곡마다 대표값 하나를 재생 순서대로 이은 선이라, 곡 안에서의 변화는 보여 주지 않아요."]
    if metric == "흐름 점수":
        notes.append(f"흰 점선이 고른 흐름('{ar.MODES[S.mode]['label']}')이에요. 추천 순서가 이 선에 가까울수록 원하는 흐름에 맞아요.")
    if metric == "빠르기" and any(raw[t]["bpm"] is None for t in org):
        notes.append("빠르기를 못 잰 곡은 점이 비어서 선이 끊겨 보여요.")
    if demo:
        notes.append("체험 모드라 그래프 값은 예시 값이에요.")
    st.html('<p class="pl-note">' + "<br>".join(ui.esc(x) for x in notes) + "</p>")

    # 지표
    def mrow(name, order):
        m = ar.evaluate(order, scores, S.mode)
        return {"순서": name, "원하는 흐름과의 차이": round(m.mae, 3), "곡 넘어갈 때 평균 변화": round(m.mean_jump, 3),
                "가장 크게 튀는 곳": round(m.max_jump, 3)}

    mrows = [mrow("원래 순서", org)] + ([mrow("추천 순서", sug)] if sug else []) + \
        ([mrow("내가 바꾼 순서", cur)] if cur != sug else [])
    st.dataframe(pd.DataFrame(mrows), hide_index=True, width="stretch")
    st.caption("숫자가 작을수록 원하는 흐름에 가깝고, 곡이 넘어갈 때 덜 튀어요. "
               "숫자는 참고용이라, 최종 판단은 직접 들어 보고 해 주세요.")

    # ── 버전 저장·비교 ──
    st.html(ui.section_html("마음에 드는 순서 저장하기"))
    vc1, vc2 = st.columns([3, 1], vertical_alignment="bottom")
    vname = vc1.text_input("이름 붙이기", key="version_name", placeholder="예: 퇴근길 고조형", max_chars=40)
    vc2.button("현재 순서 저장", icon=":material/bookmark_add:", width="stretch", on_click=save_version,
               args=(vname,))
    if ws["versions"]:
        vrows = []
        for v in ws["versions"]:
            ok = set(v["order"]) == set(tracks)
            m = ar.evaluate(v["order"], scores, S.mode) if ok else None
            vrows.append({"이름": v["name"], "저장 시각": v["created_at"].replace("T", " "),
                          "저장할 때 흐름": ar.MODES[v["settings"]["mode"]]["label"],
                          "원하는 흐름과의 차이": None if m is None else round(m.mae, 3),
                          "곡 넘어갈 때 변화": None if m is None else round(m.mean_jump, 3),
                          "상태": ("지금 순서와 같음" if ok and v["order"] == cur else
                                 ("불러올 수 있음" if ok else "곡 목록이 달라 불러올 수 없음"))})
        st.dataframe(pd.DataFrame(vrows), hide_index=True, width="stretch")
        vs1, vs2, vs3 = st.columns([2, 1, 1], vertical_alignment="bottom")
        pick = vs1.selectbox("저장한 순서", range(len(ws["versions"])), format_func=lambda i: ws["versions"][i]["name"],
                             key="version_pick")
        pick_ok = pick is not None and pick < len(ws["versions"]) and \
            set(ws["versions"][pick]["order"]) == set(tracks)
        vs2.button("불러오기", width="stretch", on_click=load_version, args=(pick,), disabled=not pick_ok)
        vs3.button("삭제", width="stretch", on_click=delete_version, args=(pick,), disabled=pick is None)
        st.caption("저장한 순서는 지금 창에만 남아요. 창을 닫거나 새로고침하면 사라지니, 아래에서 작업 파일로 받아 두세요.")
    else:
        st.caption("아직 저장한 순서가 없어요. 마음에 드는 순서에 이름을 붙여 저장하면 나중에 비교하거나 되돌릴 수 있어요.")

    # ── 내보내기·불러오기 ──
    st.html(ui.section_html("파일로 받기"))
    e1, e2 = st.columns(2)
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    e1.download_button("곡 순서 표 받기 (엑셀용 CSV)", data=storage.to_csv(cur, tracks, scores, ws["kind"]),
                       file_name=f"playline_{stamp}.csv", mime="text/csv", icon=":material/table_view:",
                       width="stretch")
    e2.download_button(
        "작업 파일 받기 (나중에 이어서 하기)", icon=":material/data_object:", width="stretch",
        data=storage.to_json(tracks=tracks, original=org, suggested=sug, current=cur, settings=settings(),
                             versions=ws["versions"], data_kind=ws["kind"],
                             excluded=[{k: e.get(k) for k in ("filename", "status", "message")} for e in ws["excluded"]]),
        file_name=f"playline_{stamp}.json", mime="application/json")
    st.caption("곡 순서 표: 순서·곡명·길이·빠르기·소리 크기. 작업 파일: 곡 목록·측정값·순서·설정·저장한 순서 (이 사이트에서 다시 열 수 있어요). "
               + storage.AUDIO_NOT_INCLUDED)

    render_import_and_help()

