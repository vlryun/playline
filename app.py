# [AI 보조 도구: Claude Code (Claude Opus 5.5),
# 작업: '기존 음원 분석 코드를 바탕으로 PLAYLINE Streamlit 웹앱 화면 구현']
"""PLAYLINE — Your tracks. Your flow.

실행:  streamlit run app.py
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from playline import analysis, arrange as ar, storage, ui
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
    flash("info", "데모를 불러왔습니다. 곡명은 공개 차트에서 확인했지만 BPM·RMS는 가상값입니다.")


def focus_upload():
    S.focus_upload = True


def run_analysis(files):
    audio = uploaded_audio(files)
    if not files:
        flash("warning", "먼저 MP3 또는 WAV 파일을 올려 주세요.")
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
        flash("error", "분석할 수 있는 곡이 없습니다. 아래 '제외된 파일' 안내를 확인해 주세요.")
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
        flash("success", f"{len(tracks)}곡 분석 결과를 갱신했습니다. 곡 구성이 같아 편집 순서와 저장 버전을 유지합니다.")
    else:
        if prev and prev["kind"] == "demo":
            flash("info", "데모 예시 데이터를 비우고 업로드한 음원의 실제 분석값으로 전환했습니다.")
        keep = [v for v in (prev or {}).get("versions", [])] if prev and prev["kind"] == "measured" else []
        S.ws = new_ws("measured", tracks, excluded=excluded, versions=keep)
        reset_pins_if_missing()
        run_arrange(silent=True)
        flash("success", f"{len(tracks)}곡을 분석했습니다. 업로드 순서를 원본 순서로 저장했고, 기본 설정으로 순서를 제안했습니다.")
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
        flash("success", f"'{ar.MODES[S.mode]['label']}' 흐름으로 순서를 제안했습니다. 아래 목록에서 직접 고칠 수 있어요.")


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
        st.button("내 음악 분석", type="primary", icon=":material/upload:", on_click=focus_upload, key="hero_upload")
        st.button("데모 체험", icon=":material/play_circle:", on_click=start_demo, key="hero_demo")

for kind, msg in S.flash:
    getattr(st, kind)(msg)
S.flash = []

left, main = st.columns([1, 2.5], gap="large")

# ─────────── 왼쪽: 설정 영역 ───────────
with left:
    with st.container(key="panel"):
        with st.container(key="focus_upload" if S.focus_upload else "upload_box"):
            st.html(ui.step_html(1, "곡 넣기"))
            files = st.file_uploader(
                "MP3·WAV 파일 (여러 개 가능)", type=["mp3", "wav"], accept_multiple_files=True,
                key=f"uploader_{S.uploader_key}",
                help=f"파일당 최대 {analysis.MAX_FILE_MB}MB. 음원은 이 앱이 실행 중인 서버(내 PC 또는 배포 서버)에서만 분석하고 외부 AI 서비스로 보내지 않으며, 분석 뒤 임시 파일을 지웁니다.")
            st.html(f'<p class="pl-help">파일당 최대 {analysis.MAX_FILE_MB}MB · 올린 순서가 원본 순서가 됩니다 · '
                    f'곡당 분석에 수 초~수십 초 걸립니다.</p>')
            audio_store = uploaded_audio(files)
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
            removed = [t["title"] for t in ws["tracks"].values() if t["sha256"] not in audio_store]
            if new_files or removed:
                msg = "업로드 목록이 현재 작업과 다릅니다."
                if new_files:
                    msg += f" 새 파일 {len(new_files)}개."
                if removed:
                    msg += f" 목록에서 빠진 곡 {len(removed)}개."
                st.warning(msg + " '분석 시작'을 눌러야 반영됩니다(이미 분석한 곡은 다시 분석하지 않습니다).")

        st.divider()
        st.html(ui.step_html(2, "원하는 흐름"))
        for mode, info in ar.MODES.items():
            sel = S.mode == mode
            with st.container(key=f"modecard_{'sel_' if sel else ''}{mode}", horizontal=True,
                              vertical_alignment="center", gap="small", wrap=False):
                st.html(ui.mode_card_html(mode, info["label"], info["desc"], sel), width="stretch")
                st.button("선택됨" if sel else "선택", key=f"mode_btn_{mode}", on_click=choose_mode, args=(mode,),
                          type="primary" if sel else "secondary", disabled=sel, width=74)

        st.divider()
        st.html(ui.step_html(3, "첫 곡·마지막 곡 고정"))
        ws = S.ws
        ids = list(ws["original"]) if ws else []
        reset_pins_if_missing()
        title_of = (lambda t: "고정 안 함" if not t else ws["tracks"][t]["title"]) if ws else (lambda t: "고정 안 함")
        pc1, pc2 = st.columns(2)
        pc1.selectbox("첫 곡", [""] + ids, format_func=title_of, key="pin_first", on_change=on_pin_change,
                      disabled=not ws)
        pc2.selectbox("마지막 곡", [""] + ids, format_func=title_of, key="pin_last", on_change=on_pin_change,
                      disabled=not ws)
        pin_error = None
        if S.pin_first and S.pin_first == S.pin_last:
            pin_error = "같은 곡을 첫 곡과 마지막 곡으로 동시에 고정할 수 없습니다. 둘 중 하나를 바꿔 주세요."
            st.error(pin_error)
        elif ws and len(ids) == 1 and (S.pin_first or S.pin_last):
            st.caption("곡이 한 곡뿐이라 고정해도 순서는 같습니다.")
        st.html('<p class="pl-help">고정한 곡은 자동 배열과 직접 수정에서 움직이지 않습니다. '
                '풀려면 \'고정 안 함\'을 고르세요.</p>')

        with st.expander("세부 설정", icon=":material/tune:"):
            st.slider("BPM 반영 비중 (%)", 0, 100, key="bpm_weight_pct", step=5,
                      help="흐름 점수 = BPM 정규화값 × 비중 + RMS 정규화값 × (1 − 비중)")
            st.caption(f"BPM {S.bpm_weight_pct}% · RMS {100 - S.bpm_weight_pct}%")
            st.slider("인접 곡 급변 완화", 0.0, 1.0, key="smooth", step=0.05,
                      help="0이면 목표 곡선과의 차이만 봅니다. 값을 올리면 바로 이웃한 곡 사이의 흐름 점수 차이가 큰 배치를 덜 고릅니다.")
            st.caption("기본값(50%, 0.2)만으로도 충분히 사용할 수 있습니다.")

        st.divider()
        stale = bool(ws and ws["suggested"] and ws["suggested_key"] != suggestion_key(ws))
        st.button("자동 배열 실행", type="primary", width="stretch", icon=":material/auto_awesome:",
                  disabled=not ws or not ws["original"] or bool(pin_error), on_click=run_arrange,
                  key="arrange_btn")
        if stale:
            st.caption("설정이 바뀌었습니다. 다시 실행하면 새 설정으로 제안합니다(현재 편집 순서는 바뀝니다).")
        elif ws and ws["original"]:
            st.caption("같은 곡 목록과 설정이면 언제나 같은 순서가 나옵니다. 무작위 섞기가 아닙니다.")


def render_import_and_help():
    """JSON 불러오기와 지표 설명. 작업 공간이 비어 있어도 쓸 수 있다."""
    with st.expander("JSON 불러오기", icon=":material/file_open:", expanded=not S.ws):
        st.caption("PLAYLINE에서 내려받은 JSON을 올리면 곡 정보·순서·설정·버전을 복원합니다. 음원은 들어 있지 않으므로, "
                   "재생하려면 왼쪽 1단계에 같은 음원 파일을 다시 올려 주세요. 파일 이름이 아니라 내용(SHA-256)이 "
                   "같을 때만 연결합니다.")
        jf = st.file_uploader("PLAYLINE JSON", type=["json"], key=f"json_{S.json_key}")
        if jf is not None:
            project, errs = storage.parse_project(jf.getvalue())
            if errs:
                st.error("불러올 수 없는 파일입니다.\n\n" + "\n".join(f"- {e}" for e in errs[:12]))
            else:
                m = storage.match_audio(project["tracks"], audio_store) if project["data_kind"] == "measured" else None
                kind_txt = "실제 분석값" if project["data_kind"] == "measured" else "데모 예시 데이터(가상값)"
                st.success(f"검증 통과 · {len(project['tracks'])}곡 · {kind_txt} · 버전 {len(project['versions'])}개")
                if m:
                    st.write(f"현재 올라온 음원과 연결: {len(m['linked'])}곡 / 누락 {len(m['missing'])}곡 / "
                             f"JSON에 없는 파일 {len(m['extra'])}개")
                    if m["missing"]:
                        st.warning("음원 미연결 (같은 파일을 올리면 연결됩니다): " +
                                   ", ".join(project["tracks"][t]["filename"] or t for t in m["missing"][:10]))
                    if m["extra"]:
                        st.info("JSON에 없는 업로드 파일은 이 작업에 넣지 않습니다: " +
                                ", ".join(audio_store[s]["filename"] for s in m["extra"][:10]))
                    for tid, newname in m["renamed"]:
                        st.caption(f"'{project['tracks'][tid]['filename']}' → 내용이 같은 '{newname}'과 연결")
                # 설정 위젯 값을 바꿔야 하므로 위젯이 만들어지기 전에 실행되는 콜백으로 처리
                st.button("이 JSON으로 작업 복원", type="primary", key="import_btn",
                          on_click=import_project, args=(project,))

    with st.expander("지표 설명", icon=":material/help:"):
        st.markdown("""
- **추정 BPM** — `librosa.beat.beat_track`으로 추정한 곡 전체의 대표 템포입니다. 실제 템포의 절반이나 두 배로 잡힐 수 있어, '곡별 분석값 · BPM 해석 조정'에서 바꿀 수 있습니다.
- **평균 RMS** — `librosa.feature.rms`로 짧은 구간마다 구한 소리 신호 크기의 평균입니다. 감정, 행복도, '신나는 정도'를 뜻하지 않습니다.
- **흐름 점수** — 이 목록 안에서 BPM과 RMS를 각각 0~1로 정규화한 뒤 반영 비중대로 섞은 **상대적 배열 지표**입니다. 다른 목록의 점수와 비교할 수 없고, 음악 감정의 객관적 점수가 아닙니다.
- **목표 곡선** — 고른 흐름(점차 고조 / 점차 차분 / 고조 후 차분)의 모양을 이 목록의 흐름 점수 범위에 맞춘 선입니다.
- **목표와의 평균 절대 오차** — 각 자리의 흐름 점수와 목표 곡선 값의 차이를 평균한 값입니다.
- **인접 곡 평균·최대 변화** — 바로 이웃한 두 곡의 흐름 점수 차이입니다.
- **자동 배열 방법** — 고정하지 않은 곡을 흐름 점수 순으로, 남은 자리를 목표값 순으로 정렬해 짝지은 뒤, '인접 곡 급변 완화' 값만큼 이웃 곡 차이를 함께 고려해 두 곡씩 자리를 바꿔 보며 개선합니다. 무작위 요소가 없어 같은 입력이면 같은 결과가 나옵니다.
""")



# ─────────── 중앙: 작업 영역 ───────────
with main:
    ws = S.ws
    if not ws or not ws["original"]:
        st.html("""
<div class="pl-empty">
  <h3>곡을 넣거나 데모로 시작해 보세요</h3>
  <p class="pl-note">PLAYLINE은 곡마다 추정 BPM과 평균 RMS(소리 신호 크기)를 계산해, 고른 흐름에 맞는 순서를 제안합니다.</p>
  <ol>
    <li><b>내 음악 분석</b> — 왼쪽 1단계에 MP3·WAV를 여러 개 올리고 '분석 시작'</li>
    <li><b>데모 체험</b> — 음원 없이 예시 데이터로 사용 흐름만 체험 (재생 불가)</li>
    <li>흐름을 고르고 '자동 배열 실행' → 그래프 비교 → 위·아래로 직접 수정 → 버전 저장</li>
  </ol>
</div>""")
        if ws and ws["excluded"]:
            st.subheader("제외된 파일")
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
        state = '<span class="pl-badge dot">자동 제안 순서</span>'
    elif cur == org:
        state = '<span class="pl-badge dot">원본 순서</span>'
    else:
        diff = sum(1 for a, b in zip(cur, sug or org) if a != b)
        state = f'<span class="pl-badge edit dot">직접 수정 중 · {"제안" if sug else "원본"}과 {diff}곡 위치 다름</span>'
    kind_badge = ('<span class="pl-badge demo dot">예시 데이터 · 가상값 (실제 측정 아님)</span>' if demo
                  else '<span class="pl-badge real dot">실제 분석값 · librosa로 계산</span>')
    linked = sum(1 for t in org if has_audio(t))
    extra = f'<span class="pl-badge">{len(org)}곡</span>'
    if not demo:
        extra += f'<span class="pl-badge">재생 가능 {linked}/{len(org)}</span>'
    if ws["from_json"]:
        extra += '<span class="pl-badge">JSON에서 불러옴</span>'
    st.html(f'<div class="pl-badges">{kind_badge}{state}{extra}</div>')
    if demo:
        st.html('<div class="pl-demo-note"><b>데모 안내</b> — 곡명·아티스트는 2026-11-19에 공개 차트에서 확인했지만, '
                'BPM·RMS는 사용 흐름을 보여주기 위한 <b>가상값</b>이며 실제 곡을 측정한 값이 아닙니다. '
                '음원이 없어 재생할 수 없습니다. 실제 분석은 왼쪽에서 파일을 올려 주세요.</div>')

    # ── 곡 목록 ──
    st.html(ui.section_html("곡 순서"))
    b1, b2, b3 = st.columns([1, 1, 2.2])
    b1.button("제안 순서로 복구", icon=":material/auto_awesome:", width="stretch", on_click=restore,
              args=("suggested",), disabled=not sug or cur == sug)
    b2.button("원본 순서로 복구", icon=":material/history:", width="stretch", on_click=restore, args=("original",),
              disabled=cur == org)
    b3.caption("위·아래 버튼으로 순서를 바꾸면 그래프와 지표가 바로 갱신됩니다. "
               "흐름 점수는 이 목록 안에서만 의미 있는 상대값입니다.")

    if S.preview_id in tracks and has_audio(S.preview_id):
        t = tracks[S.preview_id]
        a = audio_store[t["sha256"]]
        with st.container(border=True):
            st.markdown(f"**미리듣기** · {ui.esc(t['title'])}")
            st.audio(a["data"], format=a["mime"], autoplay=False)

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
                      help="이 곡을 위쪽 미리듣기 플레이어에 올립니다(자동재생 안 함)" if playable else
                      ("데모는 음원이 없어 재생할 수 없습니다" if demo else "같은 음원 파일을 다시 올리면 연결됩니다"),
                      width="content")
            up_ok = i > 0 and i not in locks and (i - 1) not in locks
            down_ok = i < n - 1 and i not in locks and (i + 1) not in locks
            st.button("", key=f"up_{tid}", icon=":material/arrow_upward:", on_click=move_track, args=(i, -1),
                      disabled=not up_ok, help="위로")
            st.button("", key=f"down_{tid}", icon=":material/arrow_downward:", on_click=move_track, args=(i, 1),
                      disabled=not down_ok, help="아래로")

    if ws["excluded"]:
        with st.expander(f"제외된 파일 {len(ws['excluded'])}개", icon=":material/error:", expanded=True):
            for e in ws["excluded"]:
                st.markdown(f"- **{ui.esc(e['filename'])}** — {e['message']}")

    with st.expander("곡별 분석값 · BPM 해석 조정", icon=":material/table_rows:"):
        st.caption("BPM은 곡 전체의 대표 추정값입니다. 비트 추정은 실제 템포의 절반이나 두 배로 잡히는 경우가 있어, "
                   "들어 보고 다르면 해석 배율을 바꿀 수 있습니다. 바꿔도 음원을 다시 분석하지 않습니다.")
        factor_label = {1.0: "추정값 그대로", 0.5: "절반으로 (½)", 2.0: "두 배로 (×2)"}
        label_factor = {v: k for k, v in factor_label.items()}
        rows = []
        for tid in org:
            t = tracks[tid]
            rows.append({"곡명": t["title"], "길이": ui.fmt_duration(t.get("duration_sec")),
                         "추정 BPM": t.get("bpm_raw"), "해석": factor_label.get(t.get("bpm_factor", 1.0)),
                         "적용 BPM": storage.effective_bpm(t), "평균 RMS": t["rms"],
                         "상태": ("가상값" if demo else ("BPM 추정 실패" if t.get("bpm_raw") is None else "분석 완료"))})
        edited = st.data_editor(
            pd.DataFrame(rows), key=f"bpm_editor_{ws['seq']}", hide_index=True, width="stretch",
            disabled=["곡명", "길이", "추정 BPM", "적용 BPM", "평균 RMS", "상태"],
            column_config={
                "해석": st.column_config.SelectboxColumn(options=list(factor_label.values()), required=True),
                "추정 BPM": st.column_config.NumberColumn(format="%.1f"),
                "적용 BPM": st.column_config.NumberColumn(format="%.1f"),
                "평균 RMS": st.column_config.NumberColumn(format="%.4f"),
            })
        changed = False
        for tid, lab in zip(org, edited["해석"]):
            f = label_factor.get(lab, 1.0)
            if tracks[tid]["bpm_raw"] is not None and tracks[tid].get("bpm_factor", 1.0) != f:
                tracks[tid]["bpm_factor"] = f
                changed = True
        if changed:
            st.rerun()

    if demo:
        with st.expander("데모 목록 편집 (곡 교체)", icon=":material/edit_note:"):
            st.caption("데모 곡명과 가상값을 바꿀 수 있습니다. 이 세션에만 적용되며, 기본 목록은 data/demo_tracks.json에서 바꿉니다.")
            df = pd.DataFrame([{"곡명": tracks[t]["title"], "아티스트": tracks[t].get("artist"),
                                "분류": tracks[t].get("category"), "BPM(가상)": tracks[t].get("bpm_raw"),
                                "RMS(가상)": tracks[t]["rms"]} for t in org])
            de = st.data_editor(df, num_rows="dynamic", key=f"demo_editor_{ws['seq']}", hide_index=True,
                                width="stretch")
            st.button("데모 목록 적용", key="apply_demo", on_click=apply_demo_edit, args=(de,))

    # ── 비교 그래프 ──
    st.html(ui.section_html("배열 전후 비교"))
    g1, g2 = st.columns([1.4, 2])
    metric = g1.segmented_control("그래프 값", ["흐름 점수", "BPM", "RMS"], default="흐름 점수", key="metric",
                                  required=True)
    version_names = [v["name"] for v in ws["versions"] if set(v["order"]) == set(tracks)]
    overlay = g2.selectbox("함께 볼 저장 버전", ["없음"] + version_names, key="overlay") if version_names else "없음"

    series = {"원본 순서": org}
    if sug:
        series["자동 제안"] = sug
    if cur != sug:
        series["직접 수정"] = cur
    if overlay != "없음":
        series[f"버전: {overlay}"] = next(v["order"] for v in ws["versions"] if v["name"] == overlay)

    lo, hi = ar.score_range(scores)
    if metric == "흐름 점수":
        values = {t: raw[t]["score"] for t in org}
        target = list(ar.target_curve(S.mode, len(org), lo, hi))
        domain = (-0.04, 1.04)
        label = "흐름 점수 (목록 내 상대값, 0~1)"
    elif metric == "BPM":
        values = {t: raw[t]["bpm"] for t in org}
        target, label = None, "추정 BPM (해석 배율 적용)"
        domain = ui.padded_domain(list(values.values()))
    else:
        values = {t: raw[t]["rms"] for t in org}
        target, label = None, "평균 RMS (소리 신호 크기)"
        domain = ui.padded_domain(list(values.values()))

    st.altair_chart(ui.flow_chart(series, tracks, values, label, domain, target, raw), theme=None,
                    width="stretch")
    notes = ["그래프는 곡마다 하나의 대표값(추정 BPM, 평균 RMS)을 재생 순서대로 이은 선입니다. "
             "곡 내부의 변화나 실제 연속 재생 파형이 아닙니다."]
    if metric == "흐름 점수":
        notes.append(f"목표 곡선은 '{ar.MODES[S.mode]['label']}' 모양을 이 목록의 흐름 점수 범위({lo:.2f}~{hi:.2f})에 맞춘 것입니다. "
                     "모든 계열이 같은 정규화 기준과 같은 축을 씁니다.")
    if metric == "BPM" and any(raw[t]["bpm"] is None for t in org):
        notes.append("BPM을 추정하지 못한 곡은 BPM 그래프에서 점이 비어 선이 끊깁니다.")
    if demo:
        notes.append("이 그래프의 값은 데모용 가상값입니다.")
    st.html('<p class="pl-note">' + "<br>".join(ui.esc(x) for x in notes) + "</p>")

    # 지표
    def mrow(name, order):
        m = ar.evaluate(order, scores, S.mode)
        return {"순서": name, "목표와의 평균 절대 오차": round(m.mae, 3), "인접 곡 평균 변화": round(m.mean_jump, 3),
                "인접 곡 최대 변화": round(m.max_jump, 3)}

    mrows = [mrow("원본 순서", org)] + ([mrow("자동 제안", sug)] if sug else []) + \
        ([mrow("직접 수정(현재)", cur)] if cur != sug else [])
    st.dataframe(pd.DataFrame(mrows), hide_index=True, width="stretch")
    st.caption("지표는 흐름 점수 기준이며 낮을수록 목표 곡선에 가깝거나 이웃 곡 사이 변화가 작다는 뜻입니다. "
               "수치가 낮아졌다고 실제로 듣기 좋아졌다는 보장은 없으니 직접 들어 보고 판단해 주세요.")

    # ── 버전 저장·비교 ──
    st.html(ui.section_html("버전 저장 · 비교"))
    vc1, vc2 = st.columns([3, 1], vertical_alignment="bottom")
    vname = vc1.text_input("버전 이름", key="version_name", placeholder="예: 퇴근길 고조형", max_chars=40)
    vc2.button("현재 순서 저장", icon=":material/bookmark_add:", width="stretch", on_click=save_version,
               args=(vname,))
    if ws["versions"]:
        vrows = []
        for v in ws["versions"]:
            ok = set(v["order"]) == set(tracks)
            m = ar.evaluate(v["order"], scores, S.mode) if ok else None
            vrows.append({"이름": v["name"], "저장 시각": v["created_at"].replace("T", " "),
                          "저장 당시 흐름": ar.MODES[v["settings"]["mode"]]["label"],
                          "목표 오차(현재 모드)": None if m is None else round(m.mae, 3),
                          "인접 평균 변화": None if m is None else round(m.mean_jump, 3),
                          "상태": ("현재 순서와 같음" if ok and v["order"] == cur else
                                 ("불러오기 가능" if ok else "곡 구성이 달라 불러올 수 없음"))})
        st.dataframe(pd.DataFrame(vrows), hide_index=True, width="stretch")
        vs1, vs2, vs3 = st.columns([2, 1, 1], vertical_alignment="bottom")
        pick = vs1.selectbox("버전 선택", range(len(ws["versions"])), format_func=lambda i: ws["versions"][i]["name"],
                             key="version_pick")
        pick_ok = pick is not None and pick < len(ws["versions"]) and \
            set(ws["versions"][pick]["order"]) == set(tracks)
        vs2.button("불러오기", width="stretch", on_click=load_version, args=(pick,), disabled=not pick_ok)
        vs3.button("삭제", width="stretch", on_click=delete_version, args=(pick,), disabled=pick is None)
        st.caption("버전은 이 브라우저 세션에만 저장됩니다. 창을 닫거나 새로고침하면 사라지므로 JSON으로 내려받아 두세요.")
    else:
        st.caption("아직 저장한 버전이 없습니다. 마음에 드는 순서에 이름을 붙여 저장하면 나중에 비교·복구할 수 있습니다.")

    # ── 내보내기·불러오기 ──
    st.html(ui.section_html("내보내기 · 불러오기"))
    e1, e2 = st.columns(2)
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    e1.download_button("CSV 다운로드 (현재 순서)", data=storage.to_csv(cur, tracks, scores, ws["kind"]),
                       file_name=f"playline_{stamp}.csv", mime="text/csv", icon=":material/table_view:",
                       width="stretch")
    e2.download_button(
        "JSON 다운로드 (전체 작업)", icon=":material/data_object:", width="stretch",
        data=storage.to_json(tracks=tracks, original=org, suggested=sug, current=cur, settings=settings(),
                             versions=ws["versions"], data_kind=ws["kind"],
                             excluded=[{k: e.get(k) for k in ("filename", "status", "message")} for e in ws["excluded"]]),
        file_name=f"playline_{stamp}.json", mime="application/json")
    st.caption("CSV: 순서·곡명·길이·BPM·RMS. JSON: 곡 식별 정보(파일명·SHA-256)·분석값·순서·설정·버전. "
               + storage.AUDIO_NOT_INCLUDED)

    render_import_and_help()

