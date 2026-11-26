# 작업 기록 (설계서 v2)

설계서: `docs/design_v2.md`. 1주차 코드와 데이터는 쓰지 않고 새로 시작했다.

## 2026-11-26 (목)

### 1. 녹음 페이지 만들기 (1단계-1, 완료)

**무엇을**: 휴대폰 크롬에서 열어 알림 앱과 같은 마이크 경로로 녹음하고, 16 kHz wav로 저장하는 페이지 (`web/`).

**왜**: 학습 데이터와 실제 사용할 때 들어오는 소리가 같아지게 하려고. 마이크 입력 부분(`web/audio-input.js`)은 알림 앱에서 그대로 다시 쓴다.

**정한 것**
- 저장소: GitHub 공개 저장소, `web/` 폴더만 GitHub Actions로 Pages 배포 (`.github/workflows/pages.yml`)
- 같은 이름의 파일을 다시 저장하면 끝에 `_t2`, `_t3` 붙임 (회차 ID는 그대로)
- Python 확인 도구: 지금 Python(3.14)에 matplotlib 설치. wav 읽기는 기본 `wave` 모듈 + numpy

**만든 파일**
- `web/audio-input.js`: 마이크(통화용 처리 3가지 끔) → 16 kHz 모노. 16 kHz AudioContext가 되면 브라우저 변환, 안 되면 AudioWorklet 안에서 JS 변환
- `web/recorder.js`: 녹음, wav(16 kHz·모노·16비트) 만들기, 파일 이름, meta.csv 줄, 화면 켜 두기(Wake Lock)
- `web/index.html`: 화면 (마이크 → 녹음 정보 → 녹음 → 저장 → 저장 기록)
- `train/check_wav.py`: wav 형식·클리핑·4 kHz 위 소리 확인, 그림 저장
- `docs/recording_setup.md`: 녹음 설정 표 (휴대폰 결과는 확인 후 채움)

**PC 시험 결과**
- JS 변환(48 kHz → 16 kHz) 사인파 시험: 6 kHz까지 0 dB, 7 kHz −2.6 dB, 앨리어싱 −87 dB 이하
- PC 크롬 158(화면 없이 실행, 가짜 마이크)에서 두 방식 모두 마이크 켜기 → 4초 녹음 → 저장까지 동작
  - 저장 파일: 16000 Hz · 모노 · 16비트, 4.00초 = 64,000샘플 (길이 정확)
  - 가짜 마이크 소리는 최대 음량이라 클리핑 경고가 떴다. 경고가 제대로 동작함을 확인

**배포**: https://munpin.github.io/sound-alert/ (저장소 https://github.com/Munpin/sound-alert)
- 처음 배포는 실패: push 때 저장소의 Pages 설정(Source: GitHub Actions)이 꺼져 있었음 → 설정 후 다시 실행해 성공

**휴대폰 확인 결과 (S24 Ultra, 안드로이드 16.0.0, 크롬 158.0.8127.42) — 4개 모두 통과**
1. 페이지 열림, 마이크 허용 창 뜸
2. getSettings: echoCancellation / noiseSuppression / autoGainControl 모두 false, 채널 1, 마이크 48 kHz
   - 16 kHz 변환: 브라우저 변환(AudioContext 16000 Hz)이 됨 → JS 변환은 예비로만 남김
3. 확인 녹음 `other_1126_s01_desk_phone.wav` (11.2초, 조용히 → 박수 → 알림음)
   - 16000 Hz · 모노 · 16비트, 클리핑 0개 (최댓값 −0.3 dBFS, 박수)
   - 4~7.8 kHz 세기: 바닥 −85.7 dB → 최대 −23.8 dB (61.9 dB 차이). 4 kHz 위 소리가 보임
   - 그림: `docs/figures/check_recording_1126.png`
4. `docs/recording_setup.md` 확정

### 2. 기록 정리 (CLAUDE.md 기록 규칙)

- `docs/progress/report_w2_1203.md` 새로 만듦 (1단계-1 정리, 재설계 배경 포함)
- 숫자 출처를 파일로 남기려고 1단계-1 시험을 다시 돌려 출력을 `docs/logs/`에 저장
  - `docs/logs/check_recording_1126.txt`: `python train/check_wav.py data/raw/other_1126_s01_desk_phone.wav --out docs/figures/check_recording_1126.png` (이전과 같은 숫자)
  - `docs/logs/resample_test_1126.txt`: JS 변환 사인파 시험 (Node)
  - `docs/logs/e2e_chrome_1126.txt`: PC 크롬 페이지 전체 시험
  - 시험 스크립트(`test_audio.mjs`, `e2e.mjs`)는 임시 폴더에서 실행했고 저장소에는 없음
- 휴대폰 설정 스크린샷의 마이크 칸만 잘라 `docs/figures/phone_settings_1126.png`로 저장 (상태 표시줄 제외)
- `recording_setup.md`에서 그림을 눈으로 읽은 숫자(6 kHz −27 dB → 8 kHz −45 dB)를 지우고 "수치 미측정"으로 고침

### 3. 녹음 회차 확인 스크립트 (1단계-2, 스크립트 완료 · 실제 회차 확인 대기)

**무엇을**: 회차 하나(wav 하나)를 녹음한 직후 돌려, 소리 개수가 맞는지와 형식·클리핑·meta.csv를 확인하는 `train/check_session.py`.

**왜**: 회차가 학습·시험 분할 단위다. 녹음 직후 개수가 틀린 걸 알아야 그 자리에서 다시 녹음할 수 있다(설계서 4절 "자동 탐지 결과가 10개인지 확인").

**사용법**

```
python train/check_session.py data/raw/doorbell_1126_s01_desk_phone.wav --expect 10
python train/check_session.py data/raw/knock_1126_s02_entrance_phone.wav --expect 10
python train/check_session.py data/raw/other_1126_s03_desk_phone.wav        # 배경만: 길이·평균 음량만
```

- 결과: 화면 + `data/checks/<파일이름>.txt`, 그림 `data/checks/<파일이름>.png`, 구간 `data/segments/<파일이름>.csv` (start,end,label)
- 개수가 다를 때
  - 작은 소리가 빠짐 → `--margin 8` (기본 12. 배경 중앙값보다 몇 dB 커야 소리로 보는지)
  - 한 번이 둘로 나뉨 → `--merge-gap 3` (기본 초인종 2.0초, 노크 1.0초)
  - 배경이 30초보다 짧았음 → `--bg-seconds 15` (기본 25초)
- meta.csv에 줄이 없으면 `[알림]`이 뜬다. 녹음 페이지 '저장 기록 → 전체 복사'로 붙여 넣는다.

**구간 찾는 방법**
1. 10 ms마다 150~7800 Hz 음량(dB)을 잰다. 아주 낮은 웅웅거림은 뺀다.
2. 앞 25초(배경)의 중앙값과 상위 5% 값을 잰다.
3. 켜짐 기준 = max(중앙값 + 12 dB, 상위 5% + 3 dB). 꺼짐 기준 = 켜짐 − 6 dB (상위 5% 아래로는 안 내려감)
4. 켜짐 기준을 넘은 곳을 꺼짐 기준 아래로 내려갈 때까지 넓힌다(소리의 울림 포함).
5. 가까운 구간을 묶는다(초인종 2초, 노크 1초). 앞 0.05초, 뒤 0.3초(노크 0.2초)를 더 붙인다.

**시험 결과** (출력: `docs/logs/session_check_synth_1126.txt`)
- 1단계-1 확인 녹음(other): 형식 16000 Hz · 1채널 · 16비트, 잘림 0개, 최댓값 31549 (−0.3 dBFS) → 이전 확인과 같음
- 합성 초인종 회차(배경 30초 + 10번, 크기 0.02~0.3): 10개 찾음, 간격 10.0초, 가장 작은 소리 배경보다 +17.9 dB
- 합성 노크 회차(배경 30초 + 10묶음, 2~3번 두드림): 10개 찾음, 간격 5.0초
- `--expect 11`로 돌리면 느낌표 경고가 뜨고 종료 코드 1
- 그림: `docs/figures/session_check_synth_1126.png`
- 참고: 확인 녹음을 노크 이름으로 바꿔 돌리면 박수 6번 + 알림음이 1초 안으로 이어져 구간 1개로 묶였고, 앞 0.1초의 짧은 소리(녹음 버튼 누른 소리로 보임)가 '배경 구간 안' 경고로 잡혔다.

**발견한 문제**
- 작은 초인종은 울림 끝이 꺼짐 기준 아래로 내려가 구간이 일찍 끝난다(합성 4번: 2.58초, 큰 소리는 4.58초). 그 꼬리가 바로 뒤 other로 들어간다. 지금은 문서 규칙대로 두고, 2단계에서 학습용 2초 창을 자를 때 처리 방법을 정한다.

## 다음 할 일
- 오늘 저녁 첫 실제 회차 녹음 → `check_session.py`로 확인
- 설계서 7절 다음 단계 진행 (다음 단계 문서를 받으면)

## 남은 문제
- 녹음을 멈출 때 마지막 50 ms 이하가 빠질 수 있다(조각 단위로 받기 때문). 10초 녹음에는 영향이 작아 그대로 둔다.
- 가까운 박수가 −0.3 dBFS로 잘림 직전. 큰 소리 녹음 때 거리 주의 (화면 클리핑 경고 확인)
- 작은 초인종의 울림 꼬리가 other 구간에 들어갈 수 있다 → 2단계(학습 창 자르기)에서 처리 (1단계-2 시험에서 발견)
