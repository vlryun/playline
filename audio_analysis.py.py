# [AI 생성 도구: ChatGPT GPT-6,
# 프롬프트: 'Nostalgia.mp3의 템포와 RMS를 분석하고 그래프로 표시하는 파이썬 코드 작성']

from pathlib import Path

import librosa
import numpy as np
import matplotlib.pyplot as plt

# 1. 파이썬 파일과 같은 폴더에 있는 음원 불러오기
folder = Path(__file__).resolve().parent
audio_path = folder / "Nostalgia.mp3"

print("음원을 불러오는 중...")
y, sr = librosa.load(audio_path, sr=22050, mono=True)

# 2. 곡의 대표 템포(BPM) 추정
print("분석 중...")
tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
bpm = float(np.asarray(tempo).item())

# 3. 구간별 RMS 계산
# RMS는 소리 신호의 크기를 나타내는 값
rms = librosa.feature.rms(y=y)[0]
times = librosa.frames_to_time(
    np.arange(len(rms)), sr=sr
)

# 4. 결과 출력
print(f"음원 길이: {len(y) / sr:.1f}초")
print(f"추정 템포: {bpm:.1f} BPM")
print(f"평균 RMS: {np.mean(rms):.4f}")

# 5. RMS 변화 그래프와 이미지 저장
plt.figure(figsize=(10, 4))
plt.plot(times, rms, color="purple")
plt.title(f"Nostalgia | Estimated tempo: {bpm:.1f} BPM")
plt.xlabel("Time (seconds)")
plt.ylabel("RMS amplitude")
plt.grid(alpha=0.3)
plt.tight_layout()
plt.savefig(folder / "analysis_result.png", dpi=150)
plt.show()