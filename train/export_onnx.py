"""임시 모델을 ONNX로 내보내고, 휴대폰 비교용 고정 입력을 만든다 (1단계-3).

하는 일
  1) 전처리 확인: 합성곱 STFT가 torch.stft와 같은 값을 내는지
  2) 임시 모델(학습 안 함)을 ONNX로 내보내기: opset 17, 입력 waveform [1, 32000], 출력 probs [1, 6]
     → web/models/temp_model.onnx
  3) Python onnxruntime으로 다시 열어 PyTorch와 출력 차이(최대 절대 차이) 재기
  4) 고정 입력 4개(무음, 1 kHz 사인파, 고정 시드 백색 잡음, 200 Hz→6 kHz 처프)와
     PyTorch 출력 확률을 web/test/fixtures.json에 저장

사용법
  python train/export_onnx.py
"""

import base64
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch

from model import build_model, load_config

ROOT = Path(__file__).resolve().parents[1]
ONNX_PATH = ROOT / "web" / "models" / "temp_model.onnx"
FIXTURE_PATH = ROOT / "web" / "test" / "fixtures.json"
OPSET = 17


def make_fixtures(sr, n):
    """코드로 만든 시험 신호 4개 (float32, -1~1)"""
    t = np.arange(n) / sr
    dur = n / sr
    f0, f1 = 200.0, 6000.0
    chirp_phase = 2 * np.pi * (f0 * t + (f1 - f0) / (2 * dur) * t ** 2)   # 선형 처프
    rng = np.random.default_rng(1234)
    sigs = {
        "silence": np.zeros(n),
        "sine_1khz": 0.5 * np.sin(2 * np.pi * 1000 * t),
        "white_noise_seed1234": np.clip(rng.normal(0, 0.1, n), -1, 1),
        "chirp_200_6000": 0.5 * np.sin(chirp_phase),
    }
    return {k: v.astype(np.float32) for k, v in sigs.items()}


def check_frontend(model, x):
    """합성곱 STFT의 파워 스펙트럼 vs torch.stft (같은 창, 같은 0 채우기)"""
    fe = model.frontend
    with torch.no_grad():
        rms = torch.sqrt(torch.mean(x * x, dim=1, keepdim=True) + 1e-12)
        rms_db = torch.clamp(20 * torch.log10(rms), min=fe.floor_db)
        xs = x * torch.pow(10.0, (fe.target_db - rms_db) / 20.0)
        xp = torch.nn.functional.pad(xs.unsqueeze(1), (fe.pad, fe.pad))
        spec = torch.nn.functional.conv1d(xp, fe.dft, stride=fe.hop)
        p_conv = spec[:, : fe.n_freqs] ** 2 + spec[:, fe.n_freqs :] ** 2
        ref = torch.stft(xs.double(), n_fft=fe.win, hop_length=fe.hop, win_length=fe.win,
                         window=torch.hann_window(fe.win, dtype=torch.float64), center=True,
                         pad_mode="constant", return_complex=True)
        p_ref = (ref.abs() ** 2).float()
    rel = (p_conv - p_ref).abs().max() / p_ref.abs().max()
    return p_conv.shape, float(rel)


def main():
    cfg = load_config()
    sr = cfg["sample_rate"]
    n = int(sr * cfg["clip_seconds"])
    print(f"torch {torch.__version__}, 클래스 {cfg['classes']}")

    model = build_model(pretrained=True, seed=0)
    n_params = sum(p.numel() for p in model.parameters())

    # 1) 전처리 확인
    fixtures = make_fixtures(sr, n)
    x_chirp = torch.from_numpy(fixtures["chirp_200_6000"])[None]
    shape, rel = check_frontend(model, x_chirp)
    with torch.no_grad():
        feat = model.frontend(x_chirp)
    print(f"[전처리] 파워 스펙트럼 모양 {tuple(shape)}, torch.stft와 최대 상대 차이 {rel:.2e}")
    print(f"[전처리] 로그 멜 모양 {tuple(feat.shape)} → 멜 {feat.shape[2]}개 × 시간 프레임 {feat.shape[3]}개")
    print(f"[모델] 파라미터 {n_params:,}개")

    # 2) ONNX 내보내기
    ONNX_PATH.parent.mkdir(parents=True, exist_ok=True)
    dummy = torch.zeros(1, n)
    t0 = time.time()
    kwargs = dict(input_names=["waveform"], output_names=["probs"], opset_version=OPSET)
    try:
        torch.onnx.export(model, (dummy,), str(ONNX_PATH), dynamo=False, **kwargs)
        how = "TorchScript 방식 (dynamo=False)"
    except TypeError:
        torch.onnx.export(model, (dummy,), str(ONNX_PATH), **kwargs)
        how = "기본 방식"
    size = ONNX_PATH.stat().st_size
    print(f"[내보내기] {ONNX_PATH.relative_to(ROOT)} ({how}, opset {OPSET}, {time.time() - t0:.1f}초)")
    print(f"[내보내기] 파일 크기 {size:,} 바이트 ({size / 1e6:.2f} MB)")

    import onnx
    m = onnx.load(str(ONNX_PATH))
    onnx.checker.check_model(m)
    ops = sorted({nd.op_type for nd in m.graph.node})
    opset = [f"{o.domain or 'ai.onnx'}:{o.version}" for o in m.opset_import]
    ins = [(i.name, [d.dim_value for d in i.type.tensor_type.shape.dim]) for i in m.graph.input]
    outs = [(o.name, [d.dim_value for d in o.type.tensor_type.shape.dim]) for o in m.graph.output]
    print(f"[ONNX] opset {opset}, 입력 {ins}, 출력 {outs}")
    print(f"[ONNX] 쓰인 연산 {len(ops)}종: {', '.join(ops)}")

    # 3) onnxruntime vs PyTorch
    import onnxruntime as ort
    sess = ort.InferenceSession(str(ONNX_PATH), providers=["CPUExecutionProvider"])
    print(f"[onnxruntime] Python onnxruntime {ort.__version__}")
    out = {"classes": cfg["classes"], "sample_rate": sr, "num_samples": n,
           "encoding": "base64 of little-endian float32", "model": "web/models/temp_model.onnx",
           "torch_version": torch.__version__, "fixtures": []}
    worst = 0.0
    for name, sig in fixtures.items():
        x = torch.from_numpy(sig)[None]
        with torch.no_grad():
            p_torch = model(x).numpy()[0]
        p_ort = sess.run(["probs"], {"waveform": sig[None]})[0][0]
        diff = float(np.abs(p_torch - p_ort).max())
        worst = max(worst, diff)
        print(f"  {name:22s} PyTorch {np.round(p_torch, 4)}  최대 차이 {diff:.2e}")
        out["fixtures"].append({
            "name": name,
            "samples_b64": base64.b64encode(sig.astype("<f4").tobytes()).decode("ascii"),
            "torch_probs": [float(v) for v in p_torch],
        })
    print(f"[onnxruntime] 고정 입력 4개 최대 절대 차이 {worst:.2e}")

    # 4) 고정 입력 저장
    FIXTURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE_PATH.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"[저장] {FIXTURE_PATH.relative_to(ROOT)} ({FIXTURE_PATH.stat().st_size:,} 바이트)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
