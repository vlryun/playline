# PLAYLINE · 플레이라인

**Your tracks. Your flow.** — 좋아하는 곡에, 나만의 흐름을.

여러 곡을 넣고 '점차 고조', '점차 차분', '고조 후 차분' 중 원하는 흐름을 고르면, 곡별 추정 BPM과 평균 RMS를 바탕으로 순서를 제안합니다. 배열 전후 그래프를 비교하고, 직접 듣고, 위·아래로 순서를 고친 뒤 버전으로 저장할 수 있습니다.

> 로컬에서 실행하는 앱입니다. 외부에 배포하지 않았으므로 공개 URL은 없습니다.

## 설치와 실행 (Windows · VS Code)

1. VS Code에서 이 폴더(`playlist-project`)를 엽니다.
2. 터미널(`Ctrl + ``)을 열고 PowerShell에서 아래 명령을 실행합니다.

가상환경을 쓰는 경우(권장):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

> `Activate.ps1` 실행이 막히면 `Set-ExecutionPolicy -Scope Process RemoteSigned` 를 먼저 실행하세요(현재 터미널 창에만 적용).

이미 전역 Python에 라이브러리를 설치했다면 바로 실행해도 됩니다.

```powershell
python -m streamlit run app.py
```

브라우저에서 http://localhost:8501 로 들어가세요(자동으로 열리지 않습니다). 종료는 터미널에서 `Ctrl + C`.

확인한 환경: Windows 11, Python 3.14.3, VS Code 1.145, 버전은 `requirements.txt` 참고.

## 사용 방법

1. **곡 넣기** — 왼쪽 1단계에 MP3·WAV 파일을 여러 개 올리고 '분석 시작'. 올린 순서가 원본 순서입니다. 음원 없이 써 보려면 '데모 체험'.
2. **원하는 흐름** — 세 가지 흐름 중 하나를 선택합니다.
3. **첫 곡·마지막 곡 고정**(선택) — 고정한 곡은 자동 배열과 직접 수정에서 움직이지 않습니다.
4. **세부 설정**(선택) — BPM·RMS 반영 비중, 인접 곡 급변 완화. 기본값으로도 충분합니다.
5. **자동 배열 실행** → 비교 그래프와 지표 확인 → 위·아래 버튼으로 수정 → '현재 순서 저장'
6. **내보내기** — CSV(순서·곡명·길이·BPM·RMS), JSON(곡 식별 정보·분석값·순서·설정·버전)

### 두 가지 모드

| | 내 음악 분석 | 흐름 체험 데모 |
|---|---|---|
| 값 | 업로드한 파일을 이 컴퓨터에서 librosa로 계산한 실제 값 | **가상값** (실제 곡 측정값 아님) |
| 재생 | 업로드한 파일만 재생 | 재생 불가 (음원 없음) |
| 표시 | '실제 분석값' 배지 | '예시 데이터 · 가상값' 배지와 안내 |

데모 곡명·아티스트는 2026-11-19에 공개 차트에서 확인했습니다. 출처는 [docs/demo_sources.md](docs/demo_sources.md).

### 알아 둘 점

- **RMS**는 소리 신호 크기의 평균입니다. 감정이나 '신나는 정도'가 아닙니다.
- **BPM**은 곡 전체의 대표 추정값이며 실제 템포의 절반·두 배로 잡힐 수 있습니다. '곡별 분석값 · BPM 해석 조정'에서 ½·×2로 바꿀 수 있습니다(재분석 없음).
- **흐름 점수**는 같은 목록 안에서 BPM·RMS를 0~1로 정규화해 섞은 상대적 배열 지표입니다.
- 무음 파일은 BPM을 추정하지 않고 배열에서 제외합니다. 박자를 찾지 못한 곡은 RMS만으로 점수를 만듭니다.
- 파일당 최대 50MB(`.streamlit/config.toml`의 `maxUploadSize`).
- 음원은 외부 서비스로 보내지 않습니다. 분석에 쓴 임시 파일은 바로 지웁니다.
- 저장한 버전과 업로드한 음원은 **브라우저 세션에만** 있습니다. 새로고침하면 사라지므로 JSON으로 내려받아 두세요. JSON에는 음원이 들어 있지 않으며, 다시 불러온 뒤 같은 음원을 올리면 **파일 내용(SHA-256)이 같을 때만** 연결합니다.

## 자동 배열 방법

1. 곡 목록 안에서 BPM과 평균 RMS를 각각 최소-최대 정규화(값이 모두 같으면 0.5)
2. 흐름 점수 = BPM 정규화값 × 비중 + RMS 정규화값 × (1 − 비중)
3. 모드별 목표 곡선(고조: 직선 상승, 차분: 직선 하강, 고조 후 차분: 60% 지점이 정점인 삼각형)을 목록의 점수 범위에 맞춤
4. 고정하지 않은 곡을 점수 순으로, 남은 자리를 목표값 순으로 정렬해 짝짓기(목표와의 절대 오차 합 최소)
5. '인접 곡 급변 완화' 값 λ만큼 이웃 곡 점수 차이를 함께 고려해, 두 곡의 자리를 바꿔 개선되면 교환을 반복

무작위 요소가 없어 같은 목록·설정이면 항상 같은 결과가 나옵니다.

## 폴더 구성

```
app.py                  화면 (Streamlit)
playline/
  analysis.py           음원 분석 (기존 코드의 분석 단계를 함수화)
  arrange.py            흐름 점수·목표 곡선·자동 배열·지표
  storage.py            CSV/JSON 저장·불러오기·검증·해시 연결
  demo.py               데모 데이터 로드
  ui.py                 화면 스타일·HTML 조각·비교 그래프
data/demo_tracks.json   데모 곡 목록 (가상값)
docs/demo_sources.md    데모 곡 출처와 확인 날짜
tests/                  단위 테스트·화면 흐름 테스트
tools/compare_legacy.py 기존 코드와 분석 결과 비교
tools/make_test_audio.py 예외 상황 확인용 합성 음원 생성
audio_analysis.py.py    기존 분석 코드 (수정하지 않고 보존)
.streamlit/config.toml  테마·업로드 크기 설정
```

## 테스트

```powershell
python -X utf8 -m unittest discover -s tests -t .
```

기존 코드와 분석 결과 비교(Nostalgia.mp3 필요):

```powershell
python -X utf8 tools\compare_legacy.py
```

예외 상황용 합성 파일 만들기(실제 음악 아님):

```powershell
python tools\make_test_audio.py test_audio
```

## 문제 해결

- **`DLL load failed ... 애플리케이션 제어 정책에서 이 파일을 차단했습니다`**: Windows '스마트 앱 컨트롤'이 numba·pandas의 DLL을 처음 불러올 때 막는 경우가 있습니다. 개발 중 두 번 나타났고, 같은 명령을 다시 실행하니 정상 동작했습니다. 계속되면 Windows 보안 설정을 확인해야 합니다.
- **터미널에 한글이 깨지거나 `UnicodeEncodeError`**: 명령에 `-X utf8`을 붙여 실행하세요.
- 첫 분석은 librosa 준비 때문에 곡당 15~20초 정도 걸릴 수 있습니다.

## 범위에서 제외한 것

로그인, 결제, 커뮤니티, 음악 생성, DJ 믹싱·곡 사이 전환 효과, 스트리밍 계정 연동, 연속 재생, 드래그 정렬.
