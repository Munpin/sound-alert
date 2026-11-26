"""녹음 페이지에서 저장한 wav 확인 (1단계 확인 3번).

확인하는 것
  1) 형식: 샘플레이트 16000, 채널 1, 16비트
  2) 잘림(클리핑): 최댓값이 끝값(32767 / -32768)에 닿았는지
  3) 높은 소리: 4 kHz 위쪽(4~8 kHz)에 소리가 남아 있는지
     - 통화용 처리나 저품질 변환이 끼면 높은 소리가 잘려 4 kHz 위가 비어 보인다.
그리고 파형 · 스펙트로그램 · 평균 스펙트럼 그림을 저장한다.

사용법
  python train/check_wav.py 파일.wav [--out 그림.png]

필요한 라이브러리: numpy, matplotlib (wav 읽기는 Python 기본 wave 모듈)
"""

import argparse
import sys
import wave
from pathlib import Path

import numpy as np

EXPECTED_RATE = 16000
N_FFT = 512        # 32 ms 창
HOP = 160          # 10 ms 간격 (모델 멜 설정과 같은 간격)


def read_wav(path):
    with wave.open(str(path), "rb") as w:
        info = {
            "rate": w.getframerate(),
            "channels": w.getnchannels(),
            "bits": 8 * w.getsampwidth(),
            "frames": w.getnframes(),
            "comptype": w.getcomptype(),
        }
        raw = w.readframes(w.getnframes())
    if info["bits"] != 16:
        raise SystemExit(f"16비트 wav가 아닙니다 ({info['bits']}비트). 이 스크립트는 16비트만 읽습니다.")
    x = np.frombuffer(raw, dtype="<i2").reshape(-1, info["channels"])
    return info, x


def spectrogram_db(x, rate):
    """x: -1~1 실수. 반환: (dB 배열 [주파수, 시간], 주파수 축, 시간 축)"""
    win = np.hanning(N_FFT).astype(np.float64)
    if len(x) < N_FFT:
        x = np.pad(x, (0, N_FFT - len(x)))
    n = 1 + (len(x) - N_FFT) // HOP
    idx = np.arange(N_FFT)[None, :] + HOP * np.arange(n)[:, None]
    frames = x[idx] * win
    power = np.abs(np.fft.rfft(frames, axis=1)) ** 2 / (win ** 2).sum()
    db = 10 * np.log10(power.T + 1e-12)
    freqs = np.fft.rfftfreq(N_FFT, 1 / rate)
    times = (np.arange(n) * HOP + N_FFT / 2) / rate
    return db, freqs, times


def load_pyplot():
    """그림 파일만 만드는 matplotlib + 한글 글꼴"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    for name in ["Malgun Gothic", "AppleGothic", "NanumGothic", "Noto Sans CJK KR"]:
        if any(f.name == name for f in matplotlib.font_manager.fontManager.ttflist):
            plt.rcParams["font.family"] = name
            break
    plt.rcParams["axes.unicode_minus"] = False
    return plt


def main():
    ap = argparse.ArgumentParser(description="녹음 wav 확인")
    ap.add_argument("wav", type=Path)
    ap.add_argument("--out", type=Path, default=None, help="그림 저장 경로 (기본: docs/figures/<파일이름>_check.png)")
    args = ap.parse_args()

    info, pcm = read_wav(args.wav)
    mono = pcm[:, 0].astype(np.int32)
    x = mono.astype(np.float64) / 32768.0
    dur = len(mono) / info["rate"]

    # ---------- 1) 형식 ----------
    fmt_ok = info["rate"] == EXPECTED_RATE and info["channels"] == 1 and info["bits"] == 16
    print(f"파일          : {args.wav.name}")
    print(f"샘플레이트    : {info['rate']} Hz")
    print(f"채널          : {info['channels']}")
    print(f"비트          : {info['bits']}")
    print(f"길이          : {dur:.2f}초 ({len(mono)} 샘플)")
    print(f"[{'통과' if fmt_ok else '실패'}] 형식 16000 Hz · 모노 · 16비트")

    # ---------- 2) 잘림 ----------
    peak = int(np.abs(mono).max()) if len(mono) else 0
    at_limit = int(np.sum((mono >= 32767) | (mono <= -32768)))
    near = int(np.sum(np.abs(mono) >= int(0.99 * 32768)))
    peak_db = 20 * np.log10(max(peak, 1) / 32768)
    clip_ok = at_limit == 0
    print(f"최댓값        : {peak} / 32768 ({peak_db:.1f} dBFS)")
    print(f"끝값에 닿은 샘플: {at_limit}개, 99% 이상: {near}개")
    print(f"[{'통과' if clip_ok else '실패'}] 클리핑 없음")

    # ---------- 3) 4 kHz 위 높은 소리 ----------
    db, freqs, times = spectrogram_db(x, info["rate"])
    power = 10 ** (db / 10)
    hi = (freqs >= 4000) & (freqs < 7800)
    lo = (freqs >= 100) & (freqs < 4000)
    hi_db = 10 * np.log10(power[hi].mean(axis=0) + 1e-12)   # 시간마다 4~7.8 kHz 평균 세기
    lo_db = 10 * np.log10(power[lo].mean(axis=0) + 1e-12)
    floor_hi = np.percentile(hi_db, 10)    # 조용한 구간(바닥) 기준
    top_hi = np.percentile(hi_db, 99)      # 가장 센 구간
    rise = top_hi - floor_hi
    hi_ok = rise >= 20
    print(f"4~7.8 kHz 세기: 바닥 {floor_hi:.1f} dB → 최대 {top_hi:.1f} dB (차이 {rise:.1f} dB)")
    print(f"[{'통과' if hi_ok else '확인 필요'}] 4 kHz 위 소리가 바닥보다 20 dB 이상 올라옴")

    # 큰 소리 구간과 조용한 구간의 평균 스펙트럼 (높은 소리가 어디까지 있는지 보기)
    total_db = 10 * np.log10(power.mean(axis=0) + 1e-12)
    order = np.argsort(total_db)
    k = max(1, len(order) // 10)
    quiet_spec = 10 * np.log10(power[:, order[:k]].mean(axis=1) + 1e-12)
    loud_spec = 10 * np.log10(power[:, order[-k:]].mean(axis=1) + 1e-12)

    # ---------- 그림 ----------
    plt = load_pyplot()
    fig, axes = plt.subplots(3, 1, figsize=(10, 9), gridspec_kw={"height_ratios": [1, 2, 1.4]})
    t = np.arange(len(x)) / info["rate"]
    axes[0].plot(t, x, lw=0.4, color="#1f5fbf")
    axes[0].axhline(1, color="#c62828", lw=0.6, ls="--")
    axes[0].axhline(-1, color="#c62828", lw=0.6, ls="--")
    axes[0].set_xlim(0, dur)
    axes[0].set_ylim(-1.05, 1.05)
    axes[0].set_ylabel("진폭")
    axes[0].set_title(f"{args.wav.name} · {info['rate']} Hz · 최대 {peak_db:.1f} dBFS · 잘림 {at_limit}개")

    vmax = np.percentile(db, 99.5)
    im = axes[1].pcolormesh(times, freqs / 1000, db, shading="auto", cmap="magma", vmin=vmax - 80, vmax=vmax)
    axes[1].axhline(4, color="#00e5ff", lw=1, ls="--")
    axes[1].text(0.01 * dur, 4.15, "4 kHz", color="#00e5ff", fontsize=9)
    axes[1].set_ylabel("주파수 (kHz)")
    axes[1].set_xlim(0, dur)
    axes[1].set_xlabel("시간 (초)")
    fig.colorbar(im, ax=axes[1], pad=0.01, label="dB")

    axes[2].plot(freqs / 1000, loud_spec, color="#c62828", lw=1, label="가장 큰 10% 구간")
    axes[2].plot(freqs / 1000, quiet_spec, color="#5d6670", lw=1, label="가장 조용한 10% 구간")
    axes[2].axvline(4, color="#1f5fbf", lw=0.8, ls="--")
    axes[2].set_xlim(0, info["rate"] / 2000)
    axes[2].set_xlabel("주파수 (kHz)")
    axes[2].set_ylabel("평균 세기 (dB)")
    axes[2].legend(loc="upper right", fontsize=9)
    axes[2].grid(alpha=0.3)
    fig.tight_layout()

    out = args.out or Path("docs/figures") / f"{args.wav.stem}_check.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=130)
    print(f"그림          : {out}")

    return 0 if (fmt_ok and clip_ok) else 1


if __name__ == "__main__":
    sys.exit(main())
