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

### 3. 녹음 회차 확인 스크립트 (1단계-2)

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

**추가: 앞뒤 잘라 내기 옵션** (사용자 지적: 녹음 시작 후 현관 밖으로 나가고 들어오는 소리)
- `--skip-start 15 --skip-end 10`: 앞 15초·뒤 10초를 배경 계산·구간 찾기·구간 목록에서 뺀다(학습에 안 씀).
- 합성 시험(발소리·문소리 앞뒤 + 초인종 10번): 옵션 없이 12개(문소리 2개를 초인종으로 셈), 옵션 켜면 10개. 기존 합성 회차 결과는 그대로 10개·10개.

**발견한 문제**
- 작은 초인종은 울림 끝이 꺼짐 기준 아래로 내려가 구간이 일찍 끝난다(합성 4번: 2.58초, 큰 소리는 4.58초). 그 꼬리가 바로 뒤 other로 들어간다. 지금은 문서 규칙대로 두고, 2단계에서 학습용 2초 창을 자를 때 처리 방법을 정한다.

### 4. 첫 실제 회차 확인 (1단계-2 완료)

**녹음**: 휴대폰 책상 위, 녹음 시작 → 밖으로 나감 → 30초 대기 → 소리 10번 → 들어와 정지. 배경: 컴퓨터 팬(`fan`).
- `doorbell_1126_s01_desk_phone_t2.wav` (250.25초. 같은 이름으로 두 번째 저장이라 `_t2`. 첫 번째 파일은 PC로 안 옮김)
- `knock_1126_s02_desk_phone.wav` (151.65초)
- 둘 다 16000 Hz · 1채널 · 16비트, 잘림 0개 (최댓값 −13.3 / −9.5 dBFS)

**1차 확인 (자르기 없이)**: 초인종 15개, 노크 17개 → 기대 10개와 다름
- 원인: 녹음 시작 후 나가는 발소리·문소리(0~19초)와 들어오는 소리(끝 10여 초)를 소리로 셈. 나가는 소리가 배경 계산에 들어가 기준도 높아짐.

**2차 확인**
```
python train/check_session.py data/raw/doorbell_1126_s01_desk_phone_t2.wav --expect 10 --skip-start 20 --skip-end 12
python train/check_session.py data/raw/knock_1126_s02_desk_phone.wav --expect 10 --skip-start 20 --skip-end 11 --drop 3,4
```
- 초인종: 10개 = 기대 10개. 길이 4.27~4.32초, 배경보다 +32.6~32.7 dB, 간격 16.9~24.1초
- 노크: 자르기만 하면 12개. 3번(67.71초, +24.4 dB, 2.19초)·4번(70.86초, +18.5 dB)은 노크보다 작고(진짜 노크 최소 +27.6 dB) 모양이 다름 → 그림을 보고 `--drop 3,4`로 other 처리 → 10개
- `--drop` 옵션 추가: 그림을 보고 잘못 잡힌 구간 번호를 other로 돌린다. 기준값(`--margin`)으로 빼기엔 노크와 차이가 2~3 dB라 불안정해서.
- 출력: `docs/logs/session_check_real_1126.txt`, 그림: `docs/figures/session_check_doorbell_1126.png`, `docs/figures/session_check_knock_1126.png`
- meta.csv: 두 회차 줄을 직접 적어 넣음(배경 fan, 휴대폰 상태 desk, note에 확인 옵션 기록) → 스크립트 meta 확인 통과

**녹음 방법 메모**: 혼자 녹음하면 앞뒤에 나가고 들어오는 소리가 들어간다 → 확인할 때 `--skip-start 20 --skip-end 12` 정도로 잘라 낸다(그림에서 위치 확인).

### 5. 휴대폰 안에서 모델 실행 확인 (1단계-3)

**무엇을**: 전처리(멜 변환)까지 넣은 임시 모델(학습 안 함)을 ONNX로 내보내 휴대폰 크롬에서 돌린다. 확인: 내보내기, PyTorch와 결과 일치, 1회 100 ms 이하.

**정한 것 (사용자 결정)**
- onnxruntime-web 1.31.1을 `web/vendor/`에 넣음 (CDN 안 씀). wasm용 약 15 MB + WebGPU 비교용 약 29 MB = 42 MB
- PyTorch GPU판: torch 2.15.0+cu132, torchvision 0.29.2+cu132 (드라이버 610.62, CUDA 13.3까지 지원 → cu132). onnx 1.23.2, onnxscript
  - 처음에 cu130/cu129/cu128/cu126 주소로 설치 시도 → 2.15.0이 없어 실패. 목록 확인 결과 2.15.0은 cu132·cu134만 있음
- 설정 파일: `train/config.json` (JSON, 라이브러리 추가 없음)

**만든 파일**
- `train/config.json`: 클래스, 음량(목표 −20, 하한 −50 dBFS), STFT(창 400, 간격 160), 멜 64개 0~8 kHz, 로그 정규화 임시값(평균 −50, 표준편차 20)
- `train/model.py`: 음량 정규화 → 합성곱 STFT(고정 DFT 가중치, 양 끝 200개 0 채움) → 멜 행렬곱 → dB·정규화 → 3채널 → MobileNetV3-Small(ImageNet) → 6개 → softmax
- `train/export_onnx.py`: 전처리 확인, ONNX 내보내기, onnxruntime 비교, `web/test/fixtures.json` 생성
- `web/model-test.html`: 고정 입력 비교, 속도(100번), 마이크 실시간(0.5초마다 최근 2초), 결과 json 저장

**결과** (출력: `docs/logs/onnx_export_1126.txt`, `docs/logs/model_test_pc_1126.txt`)
- 합성곱 STFT vs torch.stft: 최대 상대 차이 1.68e-06
- 로그 멜 모양: 64 × **201 프레임** (양 끝 0 채움 때문에 200이 아니라 201)
- 파라미터 1,524,006개, ONNX 파일 6,812,310 바이트(6.81 MB), opset 17, 연산 30종
- 내보내기: 기본 방식(dynamo)이 아니라 TorchScript 방식(`dynamo=False`)으로 opset 17을 맞춤. 출력 모양은 [배치, 6]으로 배치 칸이 이름만 있는 차원으로 기록됨(입력은 [1, 32000] 고정)
- Python onnxruntime 1.31.0 vs PyTorch: 고정 입력 4개 최대 절대 차이 2.38e-05
- PC 크롬(화면 없음) wasm: 고정 입력 4개 통과(최대 1.96e-05), 평균 20.5 ms, p95 30.3 ms, 첫 실행 65.4 ms, 모델 불러오기 737.6 ms, 1스레드
- PC 크롬 WebGPU: 모델은 불러왔으나 실행에서 응답 없음 → 미확인 (화면 없는 크롬에는 실제 GPU 없음)

**배포 실패와 해결**
- push 후 배포가 실패: 묶음(`github-pages`, 17,493,747 바이트)은 올라갔는데 `deploy-pages`가 "No artifacts named github-pages"로 못 찾음. 다시 실행(3번째 시도)해도 같음
- 액션 버전을 올림(configure-pages v6, upload-pages-artifact v5, deploy-pages v5) → 같은 오류. GitHub 상태는 정상
- 원인: 올리기와 배포를 같은 작업(job)에 두면 배포가 방금 올린 묶음을 못 찾는 deploy-pages 버그 (actions/deploy-pages issue #451)
- 해결: `.github/workflows/pages.yml`을 build 작업과 deploy 작업(needs: build) 둘로 나눔 → 성공. 배포 방식(web/ 폴더만 Pages)은 그대로

**휴대폰 결과** (S24 Ultra SM-S928N, Android 16.0.0, Chrome 158.0.8127.42, CPU 코어 8, 1스레드)
- 원본: `data/raw/model_test_1126/` (결과 json 2개, 캡처 4장). 복사본: `docs/logs/model_test_phone_wasm_1126.json`, `docs/logs/model_test_phone_webgpu_1126.json`

| 항목 | wasm (기본) | WebGPU (비교용) |
| --- | --- | --- |
| 모델 불러오기 | 3845.4 ms (내려받기 1490.5 + 세션 2354.9) | 3963.7 ms (내려받기 50.7 + 세션 3913.0) |
| 첫 실행 | 40 ms | 552.9 ms |
| 고정 입력 최대 차이 | silence 2.28e-06, sine 1.92e-06, noise 7.45e-08, chirp 1.96e-05 → **4개 통과** | silence 1.82e-06, sine 5.09e-03, noise 1.79e-02, chirp 4.18e-03 → **3개 실패** |
| 100번 평균 / p50 / p95 | **8.87 / 8.7 / 9.3 ms** | 9.32 / 8.1 / 12.6 ms |
| 최소 / 최대 | 8.5 / 15.6 ms | 5.7 / 26.2 ms |
| 마이크 실시간 | 32번 실행, 평균 21.68 ms, p95 25 ms, 최대 26.6 ms, 건너뜀 0번 (브라우저 16 kHz 변환) | 시험 안 함 |

- wasm 내려받기 1490.5 ms는 첫 방문(캐시 없음), WebGPU 쪽 50.7 ms는 같은 파일을 다시 받은 것이라 빠름
- 실시간 평균(21.7 ms)이 100번 측정(8.9 ms)보다 큰 이유: 마이크 처리와 화면 그리기가 같은 시간에 돎 (추정, 미확인)
- WebGPU 불일치: 문서 규칙대로 고치지 않고 보고함. 기본은 wasm이라 1단계 완료 기준에는 영향 없음
- 화면 버그: 실시간 확률 막대가 빈 칸으로 보임(막대 요소가 inline이라 너비 무시) → `display:block` 추가. 숫자와 측정에는 영향 없음
- 캡처: `docs/figures/phone_model_test_wasm_1126.png`, `docs/figures/phone_model_test_realtime_1126.png`, `docs/figures/phone_model_test_webgpu_1126.png`
- "0.5초마다 확률이 바뀐다": 결과 파일에는 확률 기록이 없어(실행 32번·건너뜀 0번만 기록), 막대 수정 후 휴대폰에서 다시 열어 사용자가 눈으로 확인 → 6개 막대가 움직임 (2026-11-26). 이후 결과 파일에 실행마다 확률도 저장되게 바꿈
- **1단계-3 완료 기준 4개 모두 통과 (wasm)**

## 다음 할 일
- 설계서 7절 다음 단계 진행 (다음 단계 문서를 받으면)

## 남은 문제
- 녹음을 멈출 때 마지막 50 ms 이하가 빠질 수 있다(조각 단위로 받기 때문). 10초 녹음에는 영향이 작아 그대로 둔다.
- 가까운 박수가 −0.3 dBFS로 잘림 직전. 큰 소리 녹음 때 거리 주의 (화면 클리핑 경고 확인)
- 작은 초인종의 울림 꼬리가 other 구간에 들어갈 수 있다 → 2단계(학습 창 자르기)에서 처리 (1단계-2 시험에서 발견)
