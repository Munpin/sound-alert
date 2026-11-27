"""크롬 모양 필터 확인: 백색 잡음을 to_phone_16k로 바꾼 특성이 PC 크롬 실측과 얼마나 맞는지.

사용법: python train/verify_chrome_filter.py
"""
import sys
from pathlib import Path

import numpy as np

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))
from audio_prep import SR, to_phone_16k  # noqa: E402
from compare_resample import psd, response_db  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
for rate in [48000, 44100]:
    chrome = np.fromfile(ROOT / f"data/checks/chrome_resampler/chrome_out_{rate}.f32", dtype="<f4").astype(np.float64)[SR // 2:]
    f, pc = psd(chrome)
    rc = response_db(f, pc)
    n = np.random.default_rng(1).normal(0, 0.2, rate * 11)
    out = {}
    for name, flag in [("soxr만", False), ("soxr+크롬필터", True)]:
        y = to_phone_16k(n, rate, chrome=flag)[SR // 2:-SR // 2]
        f, p = psd(y)
        out[name] = response_db(f, p)
    print(f"== 입력 {rate} Hz: 크롬 실측과의 차이 (dB) ==")
    for name, r in out.items():
        d = r - rc
        for lo, hi in [(500, 6000), (6000, 7500), (7500, 7800), (7800, 8000)]:
            m = (f >= lo) & (f < hi)
            print(f"  {name:14s} {lo / 1000:.1f}~{hi / 1000:.1f} kHz: 평균 차이 {d[m].mean():6.2f}, 최대 |차이| {np.abs(d[m]).max():6.2f}")
