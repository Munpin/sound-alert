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

## 다음 할 일
- 설계서 7절 다음 단계 진행 (다음 단계 문서를 받으면)

## 남은 문제
- 녹음을 멈출 때 마지막 50 ms 이하가 빠질 수 있다(조각 단위로 받기 때문). 10초 녹음에는 영향이 작아 그대로 둔다.
- 가까운 박수가 −0.3 dBFS로 잘림 직전. 큰 소리 녹음 때 거리 주의 (화면 클리핑 경고 확인)
