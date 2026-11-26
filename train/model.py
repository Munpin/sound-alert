"""소리 분류 모델: 16 kHz 2초 파형 → 6종 확률. 전처리까지 모두 이 모듈 안에 있다(설계서 3절 ②).

학습(PyTorch)과 휴대폰(ONNX)이 같은 계산을 하도록, 브라우저에서 확실히 도는 기본 연산만 쓴다.
  - STFT는 torch.stft 대신 합성곱(conv1d) + 고정 DFT 가중치
  - 멜 변환은 미리 만든 필터 행렬과 행렬곱

입력  waveform [배치, 32000]  (값 범위 -1~1)
출력  probs    [배치, 6]      (클래스 순서는 config.json의 classes)

순서
  1) 음량 정규화: 2초 창의 RMS를 목표값(-20 dBFS)에 맞춘다.
     RMS가 하한(-50 dBFS)보다 작으면 하한으로 계산해, 아주 조용한 소리를 목표값까지 키우지 않는다.
  2) STFT: 창 400(25 ms, Hann), 간격 160(10 ms). 양 끝에 200개씩 0을 붙여 프레임 중심을 맞춘다.
  3) 멜 필터 64개(0~8 kHz)
  4) 로그(dB) → 고정 평균·표준편차로 정규화 (지금은 임시값)
  5) 3채널 복사 → MobileNetV3-Small(ImageNet 사전학습, 마지막 층 6개) → softmax
"""

import json
import math
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

CONFIG_PATH = Path(__file__).with_name("config.json")


def load_config(path=CONFIG_PATH):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# 멜 필터 (HTK 멜 척도, 삼각형 필터). 외부 라이브러리 없이 numpy로 만든다.
# ---------------------------------------------------------------------------
def hz_to_mel(f):
    return 2595.0 * np.log10(1.0 + np.asarray(f, dtype=np.float64) / 700.0)


def mel_to_hz(m):
    return 700.0 * (10.0 ** (np.asarray(m, dtype=np.float64) / 2595.0) - 1.0)


def mel_filterbank(n_mels, n_fft, sample_rate, f_min, f_max):
    """[n_mels, n_fft//2+1] 행렬. 각 줄이 삼각형 필터 하나."""
    n_freqs = n_fft // 2 + 1
    freqs = np.linspace(0, sample_rate / 2, n_freqs)
    mel_pts = np.linspace(hz_to_mel(f_min), hz_to_mel(f_max), n_mels + 2)
    hz_pts = mel_to_hz(mel_pts)
    fb = np.zeros((n_mels, n_freqs))
    for m in range(n_mels):
        lo, ce, hi = hz_pts[m], hz_pts[m + 1], hz_pts[m + 2]
        up = (freqs - lo) / (ce - lo)
        down = (hi - freqs) / (hi - ce)
        fb[m] = np.maximum(0.0, np.minimum(up, down))
    return fb.astype(np.float32)


# ---------------------------------------------------------------------------
# 전처리 모듈: 파형 → 정규화된 로그 멜 [배치, 1, 64, 프레임]
# ---------------------------------------------------------------------------
class LogMelFrontend(nn.Module):
    def __init__(self, cfg):
        super().__init__()
        st, mel, lm, ld = cfg["stft"], cfg["mel"], cfg["log_mel"], cfg["loudness"]
        self.win = st["win_length"]
        self.hop = st["hop_length"]
        n_fft = st["n_fft"]
        assert n_fft == self.win, "n_fft와 창 길이가 같다고 가정한다"
        self.pad = n_fft // 2

        # 음량 정규화 값 (dB → 배율 계산은 forward에서)
        self.target_db = float(ld["target_dbfs"])
        self.floor_db = float(ld["floor_dbfs"])

        # DFT 가중치: 실수부 cos·창, 허수부 -sin·창 → conv1d 필터 [2*n_freqs, 1, n_fft]
        n_freqs = n_fft // 2 + 1
        n = np.arange(n_fft)
        k = np.arange(n_freqs)[:, None]
        window = 0.5 - 0.5 * np.cos(2 * np.pi * n / n_fft)  # 주기형 Hann (torch.hann_window와 같음)
        ang = 2 * np.pi * k * n / n_fft
        real = np.cos(ang) * window
        imag = -np.sin(ang) * window
        dft = np.concatenate([real, imag], axis=0)[:, None, :].astype(np.float32)
        self.register_buffer("dft", torch.from_numpy(dft))
        self.n_freqs = n_freqs

        fb = mel_filterbank(mel["n_mels"], n_fft, cfg["sample_rate"], mel["f_min"], mel["f_max"])
        self.register_buffer("mel_fb", torch.from_numpy(fb))  # [64, 201]

        self.amin = float(lm["amin"])
        self.mean = float(lm["norm_mean"])
        self.std = float(lm["norm_std"])

    def forward(self, wav):
        # 1) 음량 정규화
        rms = torch.sqrt(torch.mean(wav * wav, dim=1, keepdim=True) + 1e-12)
        rms_db = 20.0 * torch.log10(rms)
        rms_db = torch.clamp(rms_db, min=self.floor_db)          # 하한보다 조용하면 하한으로 계산
        gain = torch.pow(10.0, (self.target_db - rms_db) / 20.0)
        x = wav * gain

        # 2) STFT (합성곱)
        x = F.pad(x.unsqueeze(1), (self.pad, self.pad))          # [B, 1, 32400]
        spec = F.conv1d(x, self.dft, stride=self.hop)             # [B, 2*201, T]
        re, im = spec[:, : self.n_freqs], spec[:, self.n_freqs :]
        power = re * re + im * im                                 # [B, 201, T]

        # 3) 멜
        mel = torch.matmul(self.mel_fb, power)                    # [B, 64, T]

        # 4) 로그(dB)와 정규화
        logmel = 10.0 * torch.log10(torch.clamp(mel, min=self.amin))
        logmel = (logmel - self.mean) / self.std
        return logmel.unsqueeze(1)                                # [B, 1, 64, T]


class SoundClassifier(nn.Module):
    def __init__(self, cfg=None, pretrained=True):
        super().__init__()
        cfg = cfg or load_config()
        self.cfg = cfg
        self.frontend = LogMelFrontend(cfg)

        from torchvision.models import MobileNet_V3_Small_Weights, mobilenet_v3_small

        weights = MobileNet_V3_Small_Weights.IMAGENET1K_V1 if pretrained else None
        net = mobilenet_v3_small(weights=weights)
        in_f = net.classifier[-1].in_features
        net.classifier[-1] = nn.Linear(in_f, len(cfg["classes"]))  # 마지막 층을 6개로
        self.backbone = net

    def forward(self, waveform):
        feat = self.frontend(waveform)                            # [B, 1, 64, T]
        feat = feat.expand(-1, 3, -1, -1)                         # 3채널 복사
        logits = self.backbone(feat)
        return torch.softmax(logits, dim=1)


def build_model(pretrained=True, seed=0):
    """임시 모델(학습 안 함). 새 마지막 층의 무작위 값을 고정하려고 시드를 정한다."""
    torch.manual_seed(seed)
    model = SoundClassifier(pretrained=pretrained)
    model.eval()
    return model


if __name__ == "__main__":
    m = build_model()
    x = torch.zeros(1, int(m.cfg["sample_rate"] * m.cfg["clip_seconds"]))
    feat = m.frontend(x)
    print("로그 멜 모양:", tuple(feat.shape), "(배치, 채널, 멜, 프레임)")
    print("출력:", m(x).detach().numpy().round(4))
    print("파라미터 수:", sum(p.numel() for p in m.parameters()))
