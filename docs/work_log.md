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

## 다음 할 일
- 설계서 7절 다음 단계 진행 (다음 단계 문서를 받으면)

## 남은 문제
- 녹음을 멈출 때 마지막 50 ms 이하가 빠질 수 있다(조각 단위로 받기 때문). 10초 녹음에는 영향이 작아 그대로 둔다.
- 가까운 박수가 −0.3 dBFS로 잘림 직전. 큰 소리 녹음 때 거리 주의 (화면 클리핑 경고 확인)
- 작은 초인종의 울림 꼬리가 other 구간에 들어갈 수 있다 → 2단계(학습 창 자르기)에서 처리 (1단계-2 시험에서 발견)
