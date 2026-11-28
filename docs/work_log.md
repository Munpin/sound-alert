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

- `docs/progress/report_w3_1203.md` 새로 만듦 (1단계-1 정리, 재설계 배경 포함)
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
- WebGPU 파일 뺌 (사용자 결정): `web/vendor/`의 ort.webgpu.min.mjs, ort-wasm-simd-threaded.asyncify.{mjs,wasm} 삭제(약 29 MB), 시험 페이지의 WebGPU 버튼 삭제. 측정 결과는 `docs/logs/model_test_phone_webgpu_1126.json`에 남음

## 2026-11-27 (금)

### 1. 2단계 데이터 (진행 중, `docs/step2_data.md`)

**0. 폴더**: `data/raw/rerecord/`, `data/raw_public/{esc50,aihub,cryceleb,audioset}/`, `data/segments/` 만듦. AI Hub 원본 압축 경로는 `train/config.json`의 `paths.aihub_zip_root`에만 적음(복사 안 함).

**1. ESC-50**
- `old_sound-alert/data/raw/esc50/ESC-50-master` → `data/raw_public/esc50/ESC-50-master` 복사 (2,011개, 847 MB, `diff -rq`로 원본과 같음 확인)
- 파일 이름 두 번째 칸 = `src_file`(원본 클립 번호) 확인. 원본 클립(묶음) 1,524개
- 여러 fold에 걸친 묶음 4개(파일 9개), 그중 여러 분할에 걸친 묶음 2개(파일 5개): 209698(fold 4·5, clock_alarm·clock_tick), 234879(fold 4·5, rooster·hen). 둘 다 other. 표 만들 때(8번) 한쪽으로 모음
- 여러 종류(category)에 걸친 묶음 4개

**2-1. AI Hub 목록** (`python train/aihub.py list` → `docs/logs/aihub_list_1127.txt`)
- 소분류 24개: 교통소음 9, 생활소음 8, 사업장소음 7. 교통·생활 json 50,691개, json 하나에 소리 구간 하나
- 라벨 칸: 날짜 `info.dateCreated`, 장소 `environment.urban`(시·도)·`district`(동)·`place`(도로변/건물내부 등 장소 종류), gps(소수 둘째 자리)
- 샘플레이트 섞임: 44.1 kHz 47,739 / 48 kHz 2,919 / 22.05 kHz 23 / 32 kHz 9 / 8 kHz 1. 스테레오 10,910개
- 차량경적은 날짜 7종, 날짜+시·도+동 묶음 32개(그중 20개가 AI Hub Training·Validation 양쪽에 있음)
- **결정 (사용자 승인)**: 이륜차경적 → horn (설계서 2절 '자동차, 오토바이 경적'), '그 외' 후보 = 생활소음 8종 전부 + 차량주행음·이륜차주행음, 묶음 ID = 날짜(info.dateCreated) + 시·도(urban) + 동(district), 사업장소음·기차·지하철·비행기·헬리콥터는 안 씀. 8 kHz 파일 1개는 뺌(설계서 4절 원칙 4)
- 라이브러리 설치 (사용자 승인): soxr, yt-dlp

**2-2·2-3. AI Hub 후보 목록과 분할** (`python train/aihub.py index` → `data/raw_public/aihub/index.csv`, 출력 `docs/logs/aihub_index_1127.txt`)
- 압축 안 wav는 녹음 전체가 아니라 **라벨 소리 구간만 잘라 둔 조각**(조각 길이 = area.end − area.start, 8개 확인)
- 후보 40,095개 (horn 8,667 / siren 2,239 / other 29,189), 8 kHz 1개 뺌. 압축 방식 deflate, CRC는 표에 저장(뽑을 때 확인)
- 2초 미만 조각: horn 3,390개(39%: 차량경적 31.3%, 이륜차경적 44.6%), siren 6개, other 1,613개
- 분할(묶음 385개, 여러 분할에 걸친 묶음 0개)
  - 1차: 파일 수 비율만 맞춤 → 경적·사이렌 시험이 묶음 1개뿐(한 장소·날짜). 버림
  - 2차: 묶음 수 비율도 맞춤(가중치 파일 0.5, 묶음 1.0, 소분류 0.4) → horn 학습/검증/시험 5,444(31묶음)/1,530(5)/1,693(6), siren 1,638(67)/544(14)/57(15), other 21,539(215)/4,093(53)/3,557(52)
  - 한계: 차량경적은 날짜 7종, 한 묶음에 1,300개 이상이 몰려 시험이 20개(5묶음)뿐. horn 시험 대부분이 이륜차경적. 개(4묶음)는 검증 0개

**2-5. 크롬 변환과 soxr 비교** (`python train/compare_resample.py` → `docs/logs/resample_compare_1127.txt`, `docs/figures/resample_compare_1127.png`)
- 방법: PC 크롬 158에 백색 잡음(48 kHz, 44.1 kHz)을 넣고 녹음 페이지와 같은 경로(16 kHz AudioContext + AudioWorklet)로 받아 주파수 특성을 잼. 같은 잡음을 soxr(VHQ)로도 바꿈
- 1차 측정은 곡선이 들쭉날쭉: 브라우저에서 만든 잡음의 난수식이 JS 숫자 정밀도를 넘어 고르지 않았음 → Math.random으로 다시 잼(끊김 없음 확인)
- 크롬: −1 dB 6,375 Hz, −3 dB 6,922 Hz, −6 dB 7,359 Hz, 7.8 kHz −11.2 dB (48k→16k). 44.1k도 거의 같음
- soxr: 7,562 Hz까지 평평(−1 dB), 7.8 kHz −30.2 dB로 급하게 끊음
- 휴대폰 확인 녹음 평균 스펙트럼도 7 kHz 위에서 완만하게 줄어듦(7.0k −7.4, 7.5k −14.3 dB, 2~5 kHz 기준)
- 가정: PC 크롬과 안드로이드 크롬의 변환기가 같다(같은 Chromium 코드). 휴대폰에서 직접 백색 잡음 측정은 안 함(미확인)
- **결정 (사용자 승인)**: 공개 데이터에 크롬 모양 필터를 씌움. 2초 미만 조각은 뺌

**크롬 모양 필터** (`train/audio_prep.py`, 특성 곡선 `train/chrome_response.json`, 확인 `docs/logs/chrome_filter_verify_1127.txt`)
- 1차: soxr로 16 kHz → 크롬 곡선 FIR(129탭). 0.5~7.5 kHz는 맞았으나(6~7.5 kHz 평균 차이 0.03 dB) 7.5~8 kHz는 soxr가 이미 끊어서 크롬보다 9~62 dB 작음 → 버림
- 2차(사용): soxr로 48 kHz → 48 kHz에서 크롬 곡선 FIR(1023탭, 8 kHz 위는 kHz당 −40 dB) → 3개마다 1개. 크롬 실측과 차이: 0.5~7.8 kHz 평균 0.55 dB 이하(최대 1.83), 7.8~8.0 kHz 평균 1.64 dB(48k)·2.62 dB(44.1k)
- 직접 녹음·재녹음에는 씌우지 않음(이미 크롬을 거침)

**2-4. AI Hub 2초 창** (`python train/aihub.py extract` → `data/raw_public/aihub/wav16k/`, `windows.csv`, 출력 `docs/logs/aihub_extract_1127.txt`, 5분 11초)
- 상한: 학습 horn 600·siren 600·other 1,400(AI Hub 몫), 검증 150, 시험 300 (검증·시험 상한은 문서에 없어 정함, config에서 바꿀 수 있음). 넘으면 소분류→묶음을 돌아가며 하나씩
- 창: 조각 안에서 에너지가 가장 큰 2초, −55 dBFS 미만은 뺌(26개)
- 고른 3,707개 → 저장 3,681개. 압축 CRC 오류 0개
- horn 600/150/300, siren 600/150/57, other 1,376/148/300 (학습/검증/시험)
- 한계: horn 검증은 묶음 2개뿐, 차량경적 시험 8개(2초 이상 조건 때문에 더 줄어듦), 개(dog) 검증 0개

**1. ESC-50 2초 창** (`python train/esc50.py` → `data/raw_public/esc50/wav16k/`, `windows.csv`, 출력 `docs/logs/esc50_windows_1127.txt`)
- 크롬 모양 16 kHz, 가장 큰 2초 창. −55 dBFS 미만 2개 뺌(mouse_click, crickets) → 1,998개
- 여러 분할에 걸친 묶음 2개 → 파일 수가 많은 쪽으로 옮김: 209698 clock_tick test→val, 234879 hen val→test
- knock·baby_cry·siren·horn 각 24/8/8, other 1,102/368/368

**5. FSD50K 노크 (확인만)** (`docs/logs/fsd50k_knock_1127.txt`)
- 라벨 파일(FSD50K.ground_truth.zip, 334,701 바이트)만 받음. Knock: dev 270(train 226, val 44) + eval 103 = 373개. 모두 Door 라벨이 같이 붙음. 받을지는 사용자 결정

**4. AudioSet 아기 울음** (`python train/audioset.py download` / `sheet`, 출력 `docs/logs/audioset_download_1127.txt`, `docs/logs/audioset_bandwidth_1127.txt`)
- 평가 목록에서 /t/dd00002 정확히 60개
- 1·2차 실패: yt-dlp가 ffmpeg를 못 찾음(imageio-ffmpeg 실행 파일 이름이 ffmpeg.exe가 아님 → `data/checks/tools/ffmpeg.exe`로 복사, 구간 다운로드는 PATH만 보므로 PATH에도 추가). JS 실행기는 Node.js 지정
- 3차: **성공 33 / 60**. 실패 27개는 영상 자체가 없음: 정책 위반 삭제 10, 계정 해지 등 7, 비공개 4, 사용 불가 4, 국가 차단 2
- 50개 미만 → 설계서 8절 대안: ESC-50 울음·CryCeleb 다른 아기를 시험에 더하고 출처 겹침을 기록(예정)
- 목록 그림 `docs/figures/audioset_babycry_1_1127.png` (초록 상자 = 가장 큰 2초 자동 후보), 후보 표 `data/raw_public/audioset/cry_windows.csv`
- 대역폭 7 kHz 미만 6개: 8번 4.5, 13번 4.6, 31번 4.9, 32번 5.2, 10번 6.1, 12번 6.8 kHz (저음질 = 아기 울음 지름길 위험)

**7. 직접 녹음 처리** (`train/check_session.py` 수정, 출력 `docs/logs/session_check_real_1127.txt`)
- `--skip-start/--skip-end`(잘라서 버림) 대신 `--bg-start`, `--other-until`, `--other-from`: 나가기·들어오기 소리와 `--drop` 소리를 버리지 않고 같은 회차의 other로 남김. 구간 목록에 note 칸(walk_out/walk_in/drop/gap) 추가, 파일 전체를 빈틈없이 덮음
- `doorbell_1126_s01_desk_phone_t2.wav` → `doorbell_1126_s01_desk_phone.wav`, meta.csv note에 다시 녹음한 사실과 예전 순서 기록
- 다시 확인: 초인종 10/10 (나가기 2, 들어오기 1 → other), 노크 10/10 (나가기 5, 들어오기 1, 수동 제외 2 → other)

**3. CryCeleb**: 허깅페이스 로그인 토큰 없음 → 사용자 로그인 대기

**결정 (사용자 승인)**: AudioSet 창은 자동 후보(가장 큰 2초)를 쓰고 틀린 번호만 사용자가 알려 줌 / AudioSet 저음질 6개는 시험에서 뺌 / FSD50K 개발용(18.4 GB)만 받음(노크 270개, 묶음 = 올린 사람) / 회차 정보는 `data/sessions.csv`로 분리, `data/meta.csv`는 build_meta.py가 자동 생성
- FSD50K 노크 라이선스(개발용): CC0 166, BY 81, BY-NC 20, Sampling+ 3. 올린 사람 94명(한 사람이 48개)

**회차 정보 분리**: `data/meta.csv` → `data/sessions.csv`로 이름 바꿈. 녹음 페이지 문구('sessions.csv에 붙여 넣을 줄'), recorder.js 주석, check_session.py(`--meta` 기본값 sessions.csv), recording_setup.md 4절 수정

**8. 표와 분할 검사** (`train/build_meta.py`, `train/check_splits.py`)
- meta.csv 한 줄 = 2초 창 하나. 칸: file(data/ 아래 경로), class, source, group_id, split, place, background, phone_state, device, date, license, note, win_start
- 직접 녹음: 소리 하나에 창 하나(2초보다 길면 가장 큰 2초, 짧으면 소리를 가운데), other는 other 구간을 2초씩 자름. 소리 끝 1초·시작 0.3초 근처는 other로 안 씀(1단계-2에서 발견한 울림 꼬리 문제)
- 학습 상한(설계서 4절 other 2,400, siren·horn 600): 직접 녹음·재녹음·ESC-50은 모두 넣고 나머지 공개 데이터에서 출처·묶음을 돌아가며 채움. 처음엔 other만 상한을 걸어 siren·horn 학습이 624개(AI Hub 600 + ESC 24)였음 → 클래스별 상한으로 고침
- 지금(CryCeleb·FSD50K 전): 5,741줄, 묶음 1,932개, 여러 분할에 걸친 묶음 0개. 직접 녹음 2회차는 split 미정(unassigned)

**6. 스피커 재녹음 도구** (`train/make_playlist.py`, `train/align_rerecord.py`, 시험 출력 `docs/logs/rerecord_sim_1127.txt`)
- 재생 파일: 원본 음질(48 kHz)로, 시작 신호음 1 kHz 0.5초 + [창 2초 + 무음 2초] × n + 끝 신호음. 창마다 RMS −23 dBFS(최고점 −1 dBFS 이하)
- 자르기: 시작·끝 신호음으로 시계 차이 보정 → csv 시각대로 2초. 창 음량이 앞 무음보다 10 dB 미만이면 경고
- 1차: 창마다 음량 곡선으로 위치를 다시 잡았더니 사이렌처럼 일정한 소리에서 최대 300 ms 잘못 옮김 → 버리고 끝 신호음으로 시계 보정
- 2차 시험이 이상하게 나온 원인은 흉내 녹음을 잘못 만든 것(울림 크기 정규화로 소리가 잡음 아래로 묻힘) — 새 확인값(앞 무음 대비 0.7 dB)이 이를 잡아냄
- 신호음 시작을 20 ms 일찍 잡는 쏠림 → 분석 창 가운데 기준으로 고침
- 최종 흉내 녹음 시험(시계 +40 ppm, 울림, 잡음 −55 dBFS): 30/30개, 정답 위치와 최대 8.7 ms·평균 6.4 ms, 앞 무음 대비 21.2 dB 이상

**5. FSD50K 노크 처리** (`train/fsd50k.py`, 출력 `docs/logs/fsd50k_extract_1127.txt`, `docs/logs/fsd50k_windows_1127.txt`)
- 다운로드: 처음 한 줄씩 받기가 느려 6개 조각을 동시에 이어받기(curl)로 다시 시작. 서버 속도 제한(합계 약 1.2 MB/s) 때문에 오래 걸림. 조각 6개 모두 끝(z01~z05 각 3,221,225,472 바이트, .zip 2,306,663,327 바이트)
- `python train/fsd50k.py extract`: 반디집 명령줄로 Knock wav만 꺼냄 → 270 / 270개, 압축 오류 없음(exit 0)
- `python train/fsd50k.py windows`: Knock 270개 → 창 176개. 2초 미만 94개를 뺌(AI Hub와 같은 결정). 너무 조용한 것 0개
- 분할(올린 사람 단위): train 119개(29명), val 27개(20명), test 30개(22명)
- 창 176개 라이선스: CC0 109, CC BY 49, CC BY-NC 16, Sampling+ 2
- 메모: 분할 비율은 270개 기준으로 맞췄고, 2초 미만을 뺀 뒤 창 비율은 119:27:30

**8. 표 다시 만들기** (출력 `docs/logs/build_meta_1127b.txt`, `docs/logs/check_splits_1127b.txt`, 그림 `docs/figures/data_counts_1127.png` 갱신)
- `python train/build_meta.py` → meta.csv 5,917줄 (own 161, esc50 1,998, aihub 3,681, audioset 27, fsd50k 176)
- `python train/check_splits.py --date 1127` → 묶음 2,003개, 여러 분할에 걸친 묶음 0개(통과)
- 노크: train 143, val 35, test 38 (FSD50K 전에는 val 8, test 8)
- 남은 부족 칸: doorbell test 0·val 0(직접 녹음 split 미정), baby_cry test 35 < 50, val 8 < 20. 시험 A 비어 있음
- CryCeleb: 허깅페이스 토큰 아직 없음(다시 확인) → 사용자 로그인 대기

**3. CryCeleb2023 받기·정리** (`train/cryceleb.py summary`, 출력 `docs/logs/cryceleb_summary_1127.txt`, 그림 `docs/figures/cryceleb_durations_1127.png`)
- 사용자가 `hf auth login` 완료 → `huggingface_hub`로 README.md, metadata.csv, audio.zip(572,732,423 바이트) 받음 → 압축 검사 이상 없음, wav 26,093개 풀어 `data/raw_public/cryceleb/audio/`
- 형식: 모두 16 kHz 모노 16비트. 합계 6.51시간
- 조각 길이: 중앙값 0.78초, 90% 1.50초, 2초 이상 1,124개(4.3%)
- 녹음(아기 + 출생 B/퇴원 D) 1,334개, 녹음 하나의 조각 수 중앙값 17, 울음 합계 중앙값 15.8초
- 메타데이터에 조각 사이 간격(원래 시각)은 없음, 순서만 있음
- 대역폭: 녹음 1,334개 모두 7.5 kHz 이상(최소 7.8 kHz) → 저음질 지름길 걱정 없음
- 발견: CryCeleb 시험(test) 부분은 아기 160명이 녹음마다 다른 익명 ID(320개)로 되어 있어 같은 아기의 출생·퇴원 녹음을 묶을 수 없음 → 아기 ID 단위 분할이 깨질 수 있음
- 2초 창 방법 → 사용자에게 먼저 보고(대기)

**3. CryCeleb 2초 창** (`train/cryceleb.py windows`, 출력 `docs/logs/cryceleb_windows_1127.txt`, 예시 그림 `docs/figures/cryceleb_windows_1127.png`)
- 사용자 결정(11/27): ① 같은 녹음의 연속 조각을 0.2~0.4초 간격으로 이어 붙여 2초씩 자름(간격은 디지털 무음 대신 그 녹음 20 ms 프레임 RMS 아래 5% 크기의 잡음) ② CryCeleb test 부분은 빼고 train·dev만 씀 ③ 상한 학습 600, 검증·시험 각 150
- 아기 626명 → 아기 ID 단위 분할 train 438명, val 94명, test 94명
- 가능한 창: train 7,460, val 1,552, test 1,550 / −55 dBFS 미만이라 뺀 창 492개
- 고른 창(아기를 돌아가며 하나씩): train 600개(아기 436명), val 150개(94명), test 150개(94명). 창 하나에 든 조각 수 중앙값 2
- 저장: `wav16k/`(크롬 모양 필터), `orig2s/`(재녹음용 원본 음질 2초), `windows.csv`
- config: `cryceleb` 절 추가, `meta.train_cap`에 baby_cry 600 추가(ESC-50 24개를 먼저 넣으므로 CryCeleb 학습은 576개)
- 예시 그림에서 조각 사이 간격이 고른 잡음으로 보임. 간격 잡음은 평평한(흰) 잡음이라 지름길이 될 수 있음 → 4단계 출처별 재현율에서 확인(미확인)

**4. AudioSet 창**: 사용자 결정 = 자동 후보(가장 큰 2초) 그대로. `audioset_window_fix`, `audioset_drop` 비움

**8. 표 다시 만들기** (출력 `docs/logs/build_meta_1127c.txt`, `docs/logs/check_splits_1127c.txt`, 그림 `docs/figures/data_counts_1127.png`)
- meta.csv 6,793줄, 묶음 2,627개, 여러 분할에 걸친 묶음 0개(통과)
- 아기 울음: train 600, val 158, test 185 (ESC-50 8 + AudioSet 27 + CryCeleb 150). AudioSet 50개 미만이라 설계서 8절 대안대로 CryCeleb 다른 아기를 시험에 더함 → CryCeleb는 학습·시험 출처가 겹침(아기는 다름)
- 남은 부족 칸: doorbell val 0, test 0 (직접 녹음 split 미정). 시험 A 비어 있음(재녹음·직접 녹음 회차 필요)

**보고서 정리 중 발견**: 재녹음 흉내 시험(`docs/logs/rerecord_sim_1127.txt`)에 넣은 시계 차이 +40 ppm(122.5초 동안 4.9 ms)을 도구가 +0 ppm으로 잼. 신호음을 10 ms 단위로 찾아서 이 크기는 안 보임 → 시계 보정 동작은 미확인. 실제 재녹음 때 다시 확인
- `check_splits.py` 그림: 0개 칸도 빨강으로 (초인종 학습 0이 초록으로 보이던 것 고침)
- `docs/progress/report_w3_1203.md`에 2단계(2.4~2.7, 결과, 문제, 결정, 핵심 숫자, 예상 질문) 추가

### 2단계 결과 보고 후 수정 요청 1~6 (11/27)

**1. 경적 시험 60개, 차량·이륜차 반씩** (`train/aihub.py`, config `aihub.test_cap`·`test_cap_subcat`·`force_test_groups`)
- 차량경적 시험(2초 이상) 8개뿐 → 차량경적만 든 학습 묶음 중 같은 장소의 다른 날짜가 없는 `aihub:2021-10-26|양주시|도하리`(조각 332개)를 시험으로 옮김. 영등포동(161개)은 2021-09-04·10-13 녹음이 학습에 있어 뺌, 은현면도 날짜 2개라 뺌
- `python train/aihub.py override` (새 명령: index.csv에 강제 시험 묶음만 적용, 출력 `docs/logs/aihub_override_1127.txt`) → 경적 조각 학습 59.0 / 검증 17.7 / 시험 23.4%
- 시험 상한: horn 52 = 차량경적 22 + 이륜차경적 30 (ESC-50 car_horn 8 더해 60)
- 고르기 난수를 (분할, 클래스)마다 따로(`random.Random(f"{seed}-{split}-{cls}")`)로 바꿈 → AI Hub 창 전부 다시 만듦: `rm -rf data/raw_public/aihub/wav16k && python train/aihub.py extract` (출력 `docs/logs/aihub_extract_1127b.txt`): 3,431개, 조용해서 뺀 것 28개
- 경적 시험 묶음(`docs/logs/horn_test_groups_1127.txt`): 차량경적 22개 5묶음(도하리 14), car_horn 8개 6묶음, 이륜차경적 30개 1묶음(고양시 용두동 2021-11-12)
- 발견: AI Hub 이륜차경적은 거의 용두동. 학습에 용두동 다른 날짜 묶음 4개 → 한계로 기록(바꾸지 않음)
- meta.csv에 `subclass` 칸 추가(AI Hub 소분류, ESC-50 category, own 회차 note 등)

**2. 아기 울음 출처별** (`train/build_meta.py`, `train/make_playlist.py`, `train/check_splits.py`)
- meta.csv에 `orig_source` 칸 추가(재녹음이면 원본의 출처, rerecord_index의 orig_source). 재녹음 줄의 subclass는 원본 줄에서 물려받음
- `make_playlist.py --fill-order audioset,esc50,cryceleb`: 앞 출처를 모두 넣고 모자란 만큼만 다음 출처
- `python train/make_playlist.py --split test --cls baby_cry --n 50 --fill-order audioset,esc50,cryceleb` → 50개 = AudioSet 27 + ESC-50 8 + CryCeleb 15, 묶음 44개, 203.0초 (`docs/logs/playlist_baby_cry_test_1127.txt`)
- check_splits.py에 경적 시험 소분류별, 아기 울음 출처별 개수 출력 추가

**3. 휴대폰 크롬 변환 모양 측정** (`web/model-test.html` 4번, `train/verify_phone_resampler.py`)
- 48 kHz AudioContext의 백색 잡음 AudioBufferSource → MediaStreamAudioDestination → 16 kHz AudioContext의 MediaStreamSource → AudioWorklet로 받음. 20초(앞 0.5초 버림), 1024점 웰치 평균, 0.5~5 kHz = 0 dB. 결과 json에 곡선과 받은 소리(base64) 저장
- PC 크롬(headless) 1차: −1 dB 지점이 3,484 Hz로 나옴(잡음 한 칸이 우연히 내려감) → 20초로 늘리고 옆 5칸(약 78 Hz) 평균으로 지점 찾기
- 2차: 같은 PC에서 두 번 쟀는데 6.5 kHz 값이 −1.2 / −0.3 dB로 0.9 dB 차이 → 원인: 4초 잡음 반복 재생(서로 다른 잡음이 4초뿐) → 반복 없이 21초 잡음
- 3차(3번): −3 dB 6,953 / 6,984 / 6,984 Hz, 7.5 kHz −7.4 / −7.4 / −7.5 dB. `verify_phone_resampler.py`로 예전 PC 측정과 비교: 구간별 평균 차이 최대 0.17 dB (`docs/logs/resampler_page_pc_1127.txt`, 그림 `docs/figures/resampler_page_pc_1127.png`)
- 페이지에 `window.modelTestResult` 추가(PC 자동 시험에서 결과를 읽으려고)
- 휴대폰 측정: 미확인(사용자가 휴대폰에서 누를 예정)

**4. 직접 녹음**: `data/sessions.csv`의 split 칸을 s01(초인종), s02(노크) 모두 train으로

**5. 재녹음 시계 어긋남 보정** (`train/align_rerecord.py`, 시험 `train/sim_rerecord.py`, 출력 `docs/logs/rerecord_drift_1127.txt`)
- 보정 자체(앞뒤 신호음 사이 길이 비율)는 있었지만 신호음을 10 ms 단위로 찾아 수 ms 어긋남을 못 잼
- 고침: 대략 위치(10 ms) 뒤, 1 kHz로 내려 곱하고 16샘플 평균한 크기 곡선에서 안정 크기의 비율을 넘는 순간(샘플 단위, 소수점 보간). 같은 신호음으로 만든 기준 차이(REF_OFFSET)를 뺌
- 첫 시험: 절반 높이 기준 → 모든 창이 16.7 ms 늦음. 원인: 흉내 녹음의 울림이 커서 신호음 크기가 수십 ms 동안 쌓임 → 기준을 10%로 낮춤 (REF_OFFSET 0.97 ms)
- 결과(사이렌 시험 재생 파일 30개, 간격 122.5초): 0 / +40 / +300 / −500 / +1000 ppm을 모두 정확히 잼, 위치 오차 최대 0.80~0.86 ms. 고치기 전 방식: +40 → +82 ppm, 최대 오차 3.9~6.4 ms
- `--dry-run` 옵션 추가(파일·목록을 쓰지 않음)

**다시 만들기**: `python train/build_meta.py` (출력 `docs/logs/build_meta_1127d.txt`) → 6,403줄 / `python train/check_splits.py --date 1127` (출력 `docs/logs/check_splits_1127d.txt`) → 묶음 2,629개, 여러 분할에 걸친 묶음 0개. 부족: doorbell val 0, test 0. 시험 A 0개

**6. 보고서**: `docs/progress/report_w3_1203.md`에 2.8절(고친 것), 결과 표, 문제·결정, 핵심 숫자, 예상 질문 반영

**3. 휴대폰 크롬 변환 측정 결과** (입력 `data/raw/model_test_wasm_11270904.json`, 출력 `docs/logs/phone_resampler_1127.txt`, 그림 `docs/figures/phone_resampler_1127.png`)
- 사용자가 휴대폰(SM-S928N, Android 16.0.0, Chrome 158.0.8127.42)에서 model-test 4번 측정 → json을 data/raw/에 넣음 (json은 받은 소리가 들어 있어 1.7 MB, 저장소에 안 올림)
- `python train/verify_phone_resampler.py data/raw/model_test_wasm_11270904.json --date 1127`
- 컨텍스트 48000 → 16000 Hz, 20.00초. 휴대폰 −1/−3/−6 dB 6,547 / 6,969 / 7,375 Hz, PC(같은 계산) 6,500 / 6,922 / 7,359 Hz
- 휴대폰 − PC 평균 차이: 0.5~6.0 kHz −0.01, 6.0~7.5 kHz −0.07, 7.5~7.8 kHz 0.10 dB → PC 재측정끼리 차이(0.17 dB)보다 작음
- 결론: 휴대폰 크롬 = PC 크롬 변환. 공개 데이터 크롬 모양 필터는 그대로 씀
- 메모: 같은 PC 파일(chrome_out_48000.f32)을 이 스크립트(앞부분을 자르지 않음)로 계산하면 −1 dB가 6,500 Hz. 예전 기록 6,375 Hz(compare_resample.py)와 조금 다름 — −1 dB 근처는 기울기가 완만해 잡음에 민감

**6. 스피커 재녹음 재생 파일 6개** (`train/make_playlist.py`, 출력 `docs/logs/playlists_1127.txt`, 파일 `data/raw/rerecord/playlists/`)
- `--quota` 옵션 추가: 소분류(subclass)마다 개수. 경적은 차량(AI Hub 차량경적 + ESC-50 car_horn)과 이륜차를 반씩
- 시험: siren 30 (AI Hub 22 + ESC-50 8, 묶음 22), horn 30 (이륜차 15 + 차량경적 7 + car_horn 8, 묶음 12), baby_cry 50 (AudioSet 27 + ESC-50 8 + CryCeleb 15, 묶음 44)
- 검증: siren 25 (AI Hub 17 + ESC-50 8, 묶음 20), horn 25 (이륜차 13 + 차량경적 4 + car_horn 8, 묶음 10), baby_cry 25 (ESC-50 8 + CryCeleb 17, 묶음 20). 검증 개수는 문서 20~30 중 25로 정함
- 길이 합계: 123 + 123 + 203 + 103 × 3 = 758초(약 12.6분)
- 시험용 흉내 재생 파일 sim_siren_test는 지움

**6. 실제 스피커 재녹음 6개 자르기** (`train/align_rerecord.py`, 출력 `docs/logs/rerecord_align_1127.txt`, `docs/logs/rerecord_counts_1127.txt`)
- 사용자가 녹음: siren_1127_s01(사이렌 시험), horn_1127_s02(경적 시험), baby_cry_1127_s03(아기 울음 시험), siren_1127_s04, horn_1127_s05, baby_cry_1127_s06(검증). 노트북 스피커에서 1 m, 실제 장소 침대(장소 칸 desk). 반복 재생으로 끝 신호음 뒤에 다시 재생된 부분 있음(끝 신호음 뒤는 안 씀)
- 1차(--dry-run): 신호음 비율이 파일마다 −1 ~ −1,378 ppm으로 크게 다름 → 창마다 음량 곡선 위치를 재 보니 계단 모양: 어느 순간 한 번에 약 40 ms씩 당겨짐 = 휴대폰 녹음 중 소리 조각이 빠짐. siren_val(s04)은 빠짐 없음, 시계 차이 −1 ppm → 시계 차이는 거의 없음
- 고침 1: 창마다 재생 파일과 녹음의 음량 곡선(5 ms 간격, 앞뒤 무음 0.5초 포함)을 앞 창 위치 ±120 ms에서 맞춤(track) → 흉내 시험에서 빠짐은 따라가지만 평균 9 ms 흔들림(방 울림)
- 고침 2: 맞춘 결과는 빠진 곳 찾기에만 씀(step_levels): 20 ms 넘는 차이가 두 창 이어지면 새 구간, 구간 위치 = 구간 창들의 가운데값 − 첫 구간 가운데값. 흉내 시험(`docs/logs/rerecord_track_sim_1127.txt`, `train/sim_rerecord.py --drops`): 빠짐 0 → 최대 0.80 ms, 50 ms 6번 빠짐 → 최대 19.2 / 평균 1.75 ms(고치기 전 117.9 ms). 시계 차이 −400 ppm + 빠짐이면 55 ms(한계, 이 기기에선 해당 없음)
- 고침 3: horn s02는 시작 신호음 정밀 찾기 실패 + 첫 창부터 −78 ms → 첫 구간이 20 ms 넘게 어긋나면 맞춰 본 위치를 씀 → 일치도 가운데값 0.87 → 0.96
- 고침 4: 무음 대비를 바로 앞 무음 하나 대신 그 녹음의 모든 창 앞 무음의 가운데값과 비교 → 뺀 창 8개 → 2개(아기 울음 시험 13, 14번 AudioSet, 일치도 0.70, 0.17). 일치도 0.6 미만이나 무음 대비 10 dB 미만이면 그 창만 뺌(다시 녹음 안 함, 사용자 요청)
- 결과: 빠진 곳 s01 1번, s02 1번(+시작 신호음 도중), s03 8번, s04 0번, s05 1번, s06 1번. 마지막 창 위치와 끝 신호음 차이: s01 −40.0 / −38.3, s03 −280.0 / −279.1, s05 −37.5 / −40.0, s06 −35.0 / −40.1 ms
- 쓴 창 183 / 185: 시험 사이렌 30, 경적 30(이륜차 15, 차량경적 7, car_horn 8), 아기 울음 48(AudioSet 25, ESC-50 8, CryCeleb 15) / 검증 각 25
- `python train/build_meta.py` → 6,586줄 (`docs/logs/build_meta_1127e.txt`), `check_splits.py` → 여러 분할에 걸친 묶음 0개, 시험 A siren 30, horn 30, baby_cry 48, 없는 클래스 doorbell·knock·other (`docs/logs/check_splits_1127e.txt`)
- 미확인: 소리 빠짐 원인, 직접 녹음·실시간 알림에도 생기는지. sessions.csv에 재녹음 6개 줄 아직 없음(배경 값 받으면 추가)

- sessions.csv에 재녹음 6개 줄 추가(장소 desk·실제 침대, 배경 fan, 휴대폰 상태 desk, split 비움 — 창의 분할은 원본을 따름). align_rerecord.py 다시 실행해 장소·배경 칸 채움(결과 같음: 183 / 185), build_meta 6,586줄. 스피커 종류: 노트북 내장, 볼륨 %: 기록 없음(사용자가 기억 못 함)

### 소리 빠짐 원인 찾기 도구 (11/27, 사용자 요청: 원인 찾기 전에는 고치지 않음)

- 코드에서 찾은 후보: `web/audio-input.js` worklet의 `if (!input || input.length === 0) return true;` — 처리 블록에 마이크 입력이 비어 오면 그 블록(16 kHz에서 128샘플 = 8 ms)을 저장하지 않고 넘어감. 5블록이면 40 ms로 재녹음에서 본 크기와 같음. 확인 전이라 고치지 않음
- `web/audio-input.js`: worklet이 처리 블록마다 `currentFrame`을 보고 기록만 함(소리는 그대로)
  - gap: 앞 블록과 128 프레임 넘게 차이(블록 건너뜀), empty: 입력이 빈 블록이 이어진 구간(마이크 연결 전은 제외), zeros: 입력이 0으로만 찬 구간, tick: 약 1초마다 currentFrame·currentTime·내보낸 샘플 수
  - 메인 스레드: 받은 샘플 수, 약 1초마다 `track.stats`(크롬 마이크 통계: totalFrames, deliveredFrames 등, 있으면), 화면 보임/숨김
  - `mic.diagnostics(from, to)`: 녹음 구간만 골라 녹음 안 초(recSec)와 요약(건너뜀·빈 입력·0 구간 횟수와 ms, 벽시계 − 받은 소리, 크롬이 버린 프레임 변화)
- 녹음 페이지(`web/index.html`): wav 저장 때 같은 이름의 json도 저장, 결과 표에 진단 한 줄
- 시험 페이지(`web/model-test.html`): 결과 json에 `micDiagnostics`
- 새 페이지 `web/dropout-test.html`: 조건(음량 막대 켬/끔, 화면 밝기 최대/자동, 다른 앱 없음/유튜브) 고르고 3분(또는 1분) 자동 녹음 → 요약 표, wav + json 저장, 조건별 결과가 휴대폰에 쌓임(localStorage), 결과 표 복사
  - 음량 막대 켬 = 녹음 페이지처럼 화면마다(requestAnimationFrame) 다시 그림, 끔 = 1초에 한 번만 화면 바꿈. 밝기와 유튜브는 사용자가 직접 맞추고 고름(웹페이지가 바꿀 수 없음)
- PC 크롬(headless, 가짜 마이크) 확인: dropout-test 1분 → 건너뜀 0, 빈 입력 0, 크롬 버림 0, 벽시계 − 받은 소리 −8.4 ms(가짜 마이크는 0만 보내서 0 구간 119번). 녹음 페이지 4초 녹음 → 결과 표에 진단 줄 나옴. track.stats는 PC 크롬 158에서 읽힘
- 휴대폰 결과: 미확인(사용자 측정 대기)

**휴대폰 조건별 소리 빠짐 시험 결과** (사용자가 붙여 넣은 결과 표 → `docs/logs/dropout_test_phone_1127.json`)
- 3분씩 4조건(+ 유튜브 첫 시도 29.1초에서 멈춤, 비교에서 뺌). 유튜브는 분할화면
- 4조건 모두: 블록 건너뜀 0, 빈 입력 0, 크롬 버림(track.stats) 0, 0 구간 1번(40 ms)
- 벽시계 − 받은 소리: 막대 켬·밝기 자동·앱 없음 124.9 ms, 막대 끔 33.8 ms, 밝기 최대 19.2 ms, 유튜브 520.8 ms. 컨텍스트 시각 − 받은 소리는 모두 0
- 판단: worklet 빈 입력 후보는 아님. 0 구간 40 ms는 4번 모두 같아 녹음 시작 때로 추정(json의 recSec로 확인 필요, 미확인)
- 새 후보(미확인): AudioContext 시계가 벽시계보다 느리게 가서(휴대폰이 바쁠수록 더) 크롬이 worklet 앞단에서 넘치는 마이크 소리를 버림 → 지금 기록 장치로는 안 보임. 재녹음 빠짐(203초에 280 ms)과 크기가 비슷
- 한계: 벽시계 차이는 처음·마지막 tick(메인 스레드가 받은 시각)만 써서 메시지 지연에 흔들릴 수 있음 → 조건 사이 차이는 판단 못 함. json(1초마다 tick 전체)이 있으면 차이가 서서히 쌓였는지 한 번에 뛰었는지 확인
- 고치지 않음(사용자 요청: 원인 찾기 전에는 고치지 않음)

**소리 빠짐 json 분석** (`train/check_dropouts.py`, 입력 `data/raw/dropout_1127_*.json` 4개, 출력 `docs/logs/dropout_analysis_1127.txt`, 그림 `docs/figures/dropout_lag_1127.png`)
- 0 구간 40 ms: 4번 모두 녹음 0.04초 지점(마이크 켜는 순간) → 빠짐과 무관
- 크롬 마이크 통계: totalFrames = deliveredFrames (4번 모두). 마이크는 벽시계만큼 소리를 만들고 모두 넘겨줌(179초에 8,592,000프레임 = 179.0초)
- 마이크가 만든 소리 − 받은 소리(끝, 50 ms 조각 단위): 150 / 50 / 50 / 500 ms (막대 켬·자동 / 막대 끔 / 밝기 최대 / 유튜브)
- 벽시계 − 크롬 처리 시계(ctxTime)(끝): 125 / 34 / 19 / 521 ms, 기울기 828 / 159 / 90 / 3,223 ppm. 1초 사이 최대 변화 5~20 ms → 한 번에 뛰지 않고 조금씩 쌓임. 유튜브는 약 30초부터 계속 벌어짐
- 두 측정(마이크 통계, worklet 시계)이 서로 맞음 → 결론(가장 그럴듯함): 크롬의 소리 처리(AudioContext)가 실제 시간보다 느리게 돌고, 그만큼 넘친 마이크 소리를 크롬이 우리 코드 앞단(MediaStreamSource)에서 버림. 휴대폰이 바쁠수록(유튜브) 많이 버림. 재녹음에서 본 약 40 ms 계단은 이 버림이 조각 단위로 일어난 것으로 봄(크롬 내부라 직접 확인은 못 함)
- 음량 막대 켬/끔, 밝기: 막대 켬 두 번이 125 / 19 ms로 달라 이 4번만으로는 판단 못 함
- 실수: 처음 ppm 출력에 1000을 두 번 곱함 → 고침. 그림 제목의 빼기 기호가 글꼴에 없어 네모로 나옴 → '-'로 바꿈
- 고치지 않음. 고치는 방법은 사용자에게 먼저 보고

- 사용자 알림(11/27): 스피커 재녹음 6개(시험·검증)를 녹음하는 동안 분할 화면으로 다른 앱을 씀 → 휴대폰이 바빠 소리 빠짐이 늘었을 수 있음(조건 시험에서 유튜브 분할 화면이 3,223 ppm). 빠진 곳은 정렬 때 보정했고 183 / 185개 사용 → 다시 녹음하지 않음. sessions.csv note에 기록

- 사용자 결정(11/27): 소리 빠짐은 지금 고치지 않고 한계로 기록(받는 방식을 바꾸면 크롬 모양 필터·휴대폰 측정·재녹음을 다시 해야 함). 진단 기록 코드는 그대로 둠(소리는 바꾸지 않음, 녹음마다 json으로 남김)

**소리 빠짐 후속 (사용자 요청 1~4, 11/27)**
1. 보고서 '한계' 절 추가: 원인(크롬 처리 시계 지연 → 넘친 마이크 소리를 크롬이 버림)과 조건별 결과 표
2. 재녹음 창 안 빠짐 표시: `align_rerecord.py`에 `drop_inside()` — 빠진 곳(cuts) 앞뒤 창의 앞 끝[−0.5, 0.25초]·뒤 끝[1.75, 2.5초]을 따로 맞춰 뒤 끝이 20 ms 넘게 당겨졌으면 '1', 아니면 'near'(바로 옆 창, 불확실). `rerecord_index.csv`·`meta.csv`에 `drop_in_window` 칸(재녹음 아니면 빈칸)
   - 1차(절반[−0.5,1.0]·[1.0,2.5] 비교): 흉내 시험에서 잘못 표시 0이지만 놓침 많음(정답 4개 중 1개) → 2차(앞 끝·뒤 끝 + near): '1' 잘못 표시 0, '1'+near로 21개 중 20개 (`docs/logs/rerecord_inside_sim_1127.txt`, `train/sim_rerecord.py`에 정답 비교 추가)
   - 실제 재녹음 183개: 0 161, 1 9, near 13. 1·near 빼면 시험 아기 울음 34, 사이렌 28, 경적 28 (`docs/logs/rerecord_drop_flags_1127.txt`, `docs/logs/rerecord_align_1127.txt`)
   - 정렬 위치는 바뀌지 않음(같은 계산을 함수로 나눔). build_meta → 6,586줄, 분할 검사 통과
3. 설계서 5절 증강 실험에 '끊김 넣기: 2초 창에 40~50 ms 끊김을 무작위로' 추가
4. 설계서 메모: 알림 앱에도 빠짐 기록(mic.diagnostics)과 알림 목록을 같은 시계로 남겨 json으로 내려받게 → 오경보 측정 때 겹치는지 확인 (알림 화면 절, 측정 항목 오경보 줄)

### 설계서 새 파일 반영과 주차 번호 (11/27)

- 사용자가 `docs/design_v2.md`를 새로 바꿈 → 읽고 지금까지 작업과 비교: 맞지 않는 곳 4개 보고 → 사용자 결정으로 모두 고침
- 노크 간격: 설계서대로 5초 간격(초인종 10초). 내일 노크 회차는 5초 간격으로 녹음
- 주차 번호(설계서 1절): 1주차 = 주제·계획, 2주차 = 베이스라인(11/26), 3주차 = 지금(12/3), 4주차 = 12/10, 최종 12/17
  - 보고서 `docs/progress/report_w2_1203.md` → `report_w3_1203.md`(git mv), 제목 '3주차 진도보고서', 본문 '1주차' → '2주차 베이스라인', 다음 주 '3주차 (12/4~10)' → '4주차'
  - CLAUDE.md: 주차 구분 줄 추가, 일정·보고서 파일 이름(report_w3_1203, report_w4_1210)·재설계 배경 제목과 문장 고침
  - 다른 문서의 파일 이름 참조 고침(설계서 5절, step1_3, step2, 작업 일지). 이 일지의 앞 기록에 나온 report_w2_1203도 새 이름으로 바꿔 둠
- 설계서 8절 소리 빠짐 위험: 숫자를 로그와 맞춤(크롬 처리 시계 지연 3분에 0.02~0.13초, 덜 받은 소리 0.05~0.15초, 유튜브 0.52초 — `docs/logs/dropout_analysis_1127.txt`), 알아채는 법 '크롬 처리 시계와 실제 시간 비교'
- 설계서 4절 원칙 3: '회차 앞 30초와 소리 사이 빈 시간을 그 외로' (지금 스크립트와 같음)
- 녹음 페이지 휴대폰 상태 선택지에 shelf(선반 위) 추가 (`web/recorder.js` PHONE_STATES)
- 설계서 9절 변경 기록에 4줄 추가. 앞으로 설계가 바뀌면 9절에도 날짜·내용을 적음(사용자 요청)

## 2026-11-28

### 직접 녹음 계획: 9회차 → 18회차 (s01~s18)

**늘린 이유** (사용자 정리, 검토 후 조합 3곳 고침)
1. 초인종 학습 회차가 빠져 있었다. 처음 9회차 계획은 초인종 검증·시험만 있어서, 초인종 학습은 11/26 s01(10번)뿐이었다. 초인종은 공개 데이터가 없어 직접 녹음으로만 학습할 수 있다. 설계서 4절 목표(학습 60~80)를 채우려고 학습 7회차를 더했다.
2. 상한 80번으로 잡았다. 교수님이 "모델에 맞는 양의 데이터"를 말씀하셨고, 초인종은 녹음이 쉬워 상한까지 채우는 게 안전하다. 충분한지는 3단계 학습 곡선으로 확인한다.
3. 노크 시험이 부족했다. 휴대폰 녹음 노크 시험이 2회차(20번)면 목표 30에 못 미쳐 3회차로 늘렸다. 노크 학습에 세게·약하게를 모두 넣었다(시험에만 있는 세기가 없도록).
4. 조합 규칙: 검증·시험 회차는 학습에 없던 (장소, 배경) 조합으로 짰다. 부엌은 현관 앞과 거의 같은 자리라 같은 장소로 본다.
   - 처음 계획에서 검증 2회차(책상+말소리, 침대+말소리)가 학습과 겹쳐 화장실+말소리, 화장실+조용함으로 바꿨다.
   - 학습 '부엌+음악'은 시험 '현관+음악'과 사실상 같아 '책상+음악'으로 바꿨다.
   - 화장실 환풍기는 배경 값을 `vent`로 따로 적는다. 11/26 학습 회차의 `fan`(컴퓨터 팬)과 다른 소리다. 환풍기는 시험에만 둔다(처음 듣는 배경에서 시험).
5. 시간 분리: 같은 날이라 학습은 오전, 검증은 낮, 시험은 저녁에 녹음한다.
6. 회차 번호: 파일 이름에 날짜(1128)가 들어가 11/26 회차와 겹치지 않으므로 s01~s18. 신발장·화장실 선반은 휴대폰 상태 `shelf`.

**계획표**
| 회차 | 클래스 | 분할 | 장소 | 배경 | 휴대폰 상태 | 간격 | 메모 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| s01 | doorbell | train | entrance | water | shelf | 10초 | 싱크대 물 |
| s02 | doorbell | train | bath | water | shelf | 10초 | 문 닫고 세면대 물 |
| s03 | doorbell | train | entrance | speech | shelf | 10초 | 유튜브 말소리 |
| s04 | doorbell | train | bed | speech | blanket | 10초 | |
| s05 | doorbell | train | desk | quiet | desk | 10초 | |
| s06 | doorbell | train | desk | music | desk | 10초 | |
| s07 | doorbell | train | desk | water | desk | 10초 | 싱크대 물 |
| s08 | knock | train | entrance | quiet | shelf | 5초 | 세게 |
| s09 | knock | train | desk | speech | desk | 5초 | 약하게 |
| s10 | doorbell | val | bed | quiet | blanket | 10초 | |
| s11 | doorbell | val | bath | speech | shelf | 10초 | |
| s12 | knock | val | bath | quiet | shelf | 5초 | 보통 |
| s13 | doorbell | test | entrance | music | shelf | 10초 | |
| s14 | doorbell | test | bath | vent | shelf | 10초 | 화장실 환풍기 |
| s15 | doorbell | test | bed | music | blanket | 10초 | |
| s16 | knock | test | bed | music | blanket | 5초 | 보통 |
| s17 | knock | test | bath | vent | shelf | 5초 | 약하게, 화장실 환풍기 |
| s18 | knock | test | entrance | music | shelf | 5초 | 세게 |

**다 하면** (11/26 s01 초인종 학습·s02 노크 학습 포함): 초인종 학습 80 / 검증 20 / 시험 30, 노크(휴대폰 녹음) 학습 30 / 검증 10 / 시험 30 (노크 학습·검증에는 ESC-50, FSD50K가 더해짐)

- 계획을 `data/sessions.csv`에 미리 넣음(note 앞에 '[계획, 녹음 전]', 녹음이 들어오면 회차 확인 결과로 바꿈)
- 조합 검사 스크립트 `train/check_combos.py` (kitchen = entrance로 봄, 직접 녹음 doorbell·knock만) → `python train/check_combos.py` (출력 `docs/logs/session_combos_1128.txt`): 검증·시험이 학습과 겹치는 조합 없음(통과). 회차 수 doorbell 학습 8·검증 2·시험 3, knock 학습 3·검증 1·시험 3
- 바로잡음: 계획 설명의 "어제 s01·s02"는 11/26 녹음. 11/26 s02(노크 학습)는 책상+fan(책상+음악 아님)
- 날씨: 비. 빗소리가 들리면 메모에 rain
- 고침: s01 '부엌+조용함'은 부엌 = 현관이라 s08 '현관+조용함'과 같은 조합 → '현관+물소리(싱크대)'로 바꿈 (사용자 지적). 조합 검사 다시 → 겹침 0

### 11/28 녹음 진행

- 계획 변경(녹음 직전): 물소리 회차 3개(s01, s02, s07) 뺌 — 조금만 틀어도 휴대폰 '평균' −27 dB로 초인종(11/26 책상, 평균 약 −37 dB, 최대 약 −28 dB)보다 큼. 원룸이라 더 멀리 둘 곳 없음 → s01 화장실+음악, s02 책상+fan(11/26 학습과 같은 조합), s07 현관+조용함(s08과 같은 조합). 조합 검사 다시 → 겹침 0. 배경(음악·말소리)은 노트북 유튜브로, 배경만 틀어 '평균' −45 dB 이하
- 초인종 고장(사용자, 비 오는 날) → 오늘은 노크 회차(8, 9, 12, 16, 17, 18)만. 초인종 회차는 고친 뒤
- 파일 위치: 사용자가 `data/raw/self_record/`에 넣음 → `build_meta.py`가 raw/에 없으면 raw/self_record/에서 찾게 고침
- **s08 (knock 학습, 현관+조용함, 신발장 위, 세게)**: `python train/check_session.py data/raw/self_record/knock_1128_s08_entrance_phone.wav --expect 10 --other-until 41 --other-from 112 --drop 11` → 10/10 통과 (`data/checks/knock_1128_s08_entrance_phone.txt`, .png)
  - 123.55초, 최대 −3.1 dBFS, 잘림 0. 배경 중앙값 −53.0 dB. 노크 +50.1~+62.1 dB, 실제 간격 5.8~8.2초
  - other: 기다리는 동안 소리 2개(12.8초 +45.2 dB 짧은 딸깍, 24.3초 +15.8 dB), 나가기(32.1~41.0초), 작은 딸깍(79.6초 +15.6 dB, --drop), 들어오기(112.5초~)
  - 소리 빠짐 기록(json): 블록 건너뜀·빈 입력·0 구간 0, 벽시계 − 받은 소리 24.8 ms
- **s09 (knock 학습, 책상+말소리(노트북 뉴스), 책상 위, 약하게)**
  - 녹음 때 회차 칸을 8로 둬서 사용자가 파일 이름을 s09로 바꿈 → json의 file 칸도 s09로 고치고 renamedFrom 기록
  - 1차 녹음: 뉴스가 커서 배경 중앙값 −36.5 dB(s08 조용함 −53.0 dB). 찾은 구간 28개, 낮은 소리(40~200 Hz)로 보면 약 7초 간격 후보가 있지만 뉴스보다 15~20 dB뿐이라 10개 확신 못 함 → 다시 녹음 권함. 안내 실수: 녹음 페이지 '평균'(50 ms 조각 RMS)과 스크립트 dB(150~7800 Hz 프레임)가 달라, 페이지 −50~−40이 기준(−45)보다 큰 소리였음 → 말소리·음악 배경은 페이지 평균 −55 dB 아래로 안내
  - 2차 녹음: 배경 중앙값 −41.6 dB. 자동 구간 17개 중 노크 9개(59.3~113.0초, 간격 6.0~7.3초)가 분명. 10번째는 나가며 문 닫는 소리(50.44~53.55초)에 붙어 있었음 → 노크 9개 평균 스펙트럼과 비교해 52.78초가 닮음 0.94(노크끼리 평균 0.95), 다음 노크와 7.6초 → 노크로 판단
  - `check_session.py`에 `--split` 추가(찾은 구간을 지정 시각에서 둘로 자름). `python train/check_session.py data/raw/self_record/knock_1128_s09_desk_phone.wav --expect 10 --split 52.7 --other-until 52.7 --other-from 119.5` → 10/10 통과. 노크는 배경보다 +20.6~+27.3 dB
  - 메모: 52.7초 노크의 2초 창에는 바로 앞 문 닫는 소리 끝이 섞일 수 있음
  - 소리 빠짐 기록: 0 (벽시계 − 받은 소리 14.1 ms)

## 다음 할 일
- 2단계 남은 일(사용자): 초인종 검증·시험용 회차 (시험 A의 초인종·노크·그 외)
- 설계서 7절 다음 단계 진행 (다음 단계 문서를 받으면)

## 남은 문제
- 휴대폰 녹음 중 소리 빠짐: 크롬 소리 처리 시계가 실제 시간보다 늦어져 넘친 마이크 소리를 크롬이 버림(3분에 19~125 ms, 바쁘면 521 ms). 한계로 기록, 고치지 않음(11/27)
- 녹음을 멈출 때 마지막 50 ms 이하가 빠질 수 있다(조각 단위로 받기 때문). 10초 녹음에는 영향이 작아 그대로 둔다.
- 가까운 박수가 −0.3 dBFS로 잘림 직전. 큰 소리 녹음 때 거리 주의 (화면 클리핑 경고 확인)
- 작은 초인종의 울림 꼬리가 other 구간에 들어갈 수 있다 → 2단계(학습 창 자르기)에서 처리 (1단계-2 시험에서 발견)
