# [AI 생성 도구: ChatGPT GPT-6,
# 프롬프트: 'Nostalgia.mp3의 템포와 RMS를 분석하고 그래프로 표시하는 파이썬 코드 작성']
# 위 주석은 원본 audio_analysis.py.py에서 가져온 출처 표기이며, 원본 파일은 그대로 보존한다.
# 이 모듈은 원본의 분석 단계(불러오기 → beat_track 템포 추정 → RMS 평균)를
# 같은 파라미터로 함수화하고, 여러 파일 처리·오류·무음 판정을 추가했다.
# [AI 보조 도구: Claude Code (Claude Opus 5.5),
# 작업: '기존 분석 코드를 PLAYLINE 웹앱에서 재사용할 수 있도록 모듈화하고 예외 처리 추가']
"""음원 분석.

모든 분석은 앱이 실행 중인 서버(로컬 PC 또는 배포 서버)에서 librosa로 수행하며, 음원을 외부 AI 서비스로 전송하지 않는다.

값의 의미
- bpm      : librosa.beat.beat_track으로 추정한 곡 전체 대표 템포. 실제 템포의
             절반·두 배로 추정될 수 있다(tempo octave error).
- rms_mean : librosa.feature.rms 프레임 값의 평균. 소리 신호 크기의 지표이며
             감정이나 '신나는 정도'를 뜻하지 않는다.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass, field, asdict
from pathlib import Path

import numpy as np

# 원본 코드와 동일한 분석 조건
SAMPLE_RATE = 22050
MONO = True

# 업로드 파일 하나당 허용 크기 (.streamlit/config.toml 의 maxUploadSize 와 맞춘다)
MAX_FILE_MB = 50
SUPPORTED_EXTS = {".mp3", ".wav"}

# 무음 판정 기준: 최대 진폭과 평균 RMS가 모두 이 값보다 작으면 무음으로 본다
SILENCE_PEAK = 1e-3
SILENCE_RMS = 1e-4
# 비트가 이보다 적게 잡히면 BPM 추정 실패로 본다
MIN_BEATS = 4


@dataclass
class TrackAnalysis:
    """곡 하나의 분석 결과."""

    filename: str
    sha256: str
    size_bytes: int
    status: str  # "ok" | "bpm_failed" | "silent" | "error"
    message: str = ""
    duration_sec: float | None = None
    bpm: float | None = None
    rms_mean: float | None = None
    beat_count: int | None = None
    bpm_alternatives: list[float] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def usable(self) -> bool:
        """배열에 쓸 수 있는 값(최소한 RMS)이 있는지."""
        return self.status in ("ok", "bpm_failed") and self.rms_mean is not None


def file_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def analyze_signal(y: np.ndarray, sr: int) -> dict:
    """원본 코드의 2~4단계(템포 추정, RMS 계산, 결과 값)를 그대로 수행한다."""
    import librosa

    duration = len(y) / sr

    # 2. 곡의 대표 템포(BPM) 추정 (원본과 동일)
    tempo, beats = librosa.beat.beat_track(y=y, sr=sr)
    bpm = float(np.asarray(tempo).item())

    # 3. 구간별 RMS 계산 (원본과 동일). RMS는 소리 신호의 크기를 나타내는 값
    rms = librosa.feature.rms(y=y)[0]
    rms_mean = float(np.mean(rms)) if rms.size else 0.0

    return {
        "duration_sec": float(duration),
        "bpm": bpm,
        "rms_mean": rms_mean,
        "beat_count": int(len(beats)),
        "peak": float(np.max(np.abs(y))) if y.size else 0.0,
    }


def _load(path: str | os.PathLike):
    import librosa

    # 1. 음원 불러오기 (원본과 동일: 22,050Hz 모노)
    return librosa.load(path, sr=SAMPLE_RATE, mono=MONO)


def analyze_path(path: str | os.PathLike, filename: str | None = None,
                 data: bytes | None = None) -> TrackAnalysis:
    """경로의 음원을 분석한다. 실패해도 예외 대신 status로 알려준다."""
    path = Path(path)
    filename = filename or path.name
    if data is None:
        data = path.read_bytes()
    sha = file_sha256(data)
    size = len(data)

    base = dict(filename=filename, sha256=sha, size_bytes=size)

    if size == 0:
        return TrackAnalysis(**base, status="error", message="빈 파일입니다.")

    try:
        y, sr = _load(path)
    except Exception as exc:  # 깨진 파일, 지원하지 않는 코덱 등
        return TrackAnalysis(
            **base, status="error",
            message=f"음원을 읽을 수 없습니다. 파일이 손상되었거나 지원하지 않는 형식일 수 있습니다. ({type(exc).__name__})",
        )

    if y is None or len(y) == 0:
        return TrackAnalysis(**base, status="error", message="음원에 소리 데이터가 없습니다.")
    if not np.all(np.isfinite(y)):
        return TrackAnalysis(**base, status="error", message="음원 데이터에 읽을 수 없는 값이 있습니다.")

    try:
        res = analyze_signal(y, sr)
    except Exception as exc:
        return TrackAnalysis(
            **base, status="error", duration_sec=len(y) / sr,
            message=f"분석 중 오류가 발생했습니다. ({type(exc).__name__})",
        )

    common = dict(duration_sec=res["duration_sec"], beat_count=res["beat_count"])

    if res["peak"] < SILENCE_PEAK and res["rms_mean"] < SILENCE_RMS:
        # 무음: 템포를 꾸며내지 않는다. RMS는 실제 계산값(≈0)이지만 배열에서는 제외한다.
        return TrackAnalysis(
            **base, **common, status="silent", rms_mean=res["rms_mean"],
            message="소리가 거의 없는 무음 파일로 판단되어 BPM을 추정하지 않았고 배열에서 제외합니다.",
        )

    bpm = res["bpm"]
    if not np.isfinite(bpm) or bpm <= 0 or res["beat_count"] < MIN_BEATS:
        return TrackAnalysis(
            **base, **common, status="bpm_failed", rms_mean=res["rms_mean"],
            message="박자를 충분히 찾지 못해 BPM을 추정하지 못했습니다. 이 곡의 흐름 점수는 RMS만으로 계산합니다.",
        )

    return TrackAnalysis(
        **base, **common, status="ok", bpm=bpm, rms_mean=res["rms_mean"],
        bpm_alternatives=[round(bpm / 2, 1), round(bpm * 2, 1)],
    )


def analyze_bytes(data: bytes, filename: str) -> TrackAnalysis:
    """업로드된 바이트를 임시 파일에 써서 분석한 뒤 임시 파일을 지운다.

    임시 파일 이름은 ASCII로 만들어 한글·공백이 들어간 원래 파일명과 무관하게 동작한다.
    """
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_EXTS:
        return TrackAnalysis(
            filename=filename, sha256=file_sha256(data), size_bytes=len(data),
            status="error", message="MP3 또는 WAV 파일만 분석할 수 있습니다.",
        )
    if len(data) > MAX_FILE_MB * 1024 * 1024:
        return TrackAnalysis(
            filename=filename, sha256=file_sha256(data), size_bytes=len(data),
            status="error", message=f"파일이 {MAX_FILE_MB}MB를 넘어 분석하지 않았습니다.",
        )

    fd, tmp = tempfile.mkstemp(prefix="playline_", suffix=ext)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        return analyze_path(tmp, filename=filename, data=data)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def title_from_filename(filename: str) -> str:
    """파일명에서 확장자를 떼고 밑줄을 공백으로 바꿔 제목으로 쓴다."""
    stem = Path(filename).stem.replace("_", " ").strip()
    return stem or filename
