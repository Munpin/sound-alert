"""2-5: 휴대폰 크롬의 16 kHz 변환과 Python(soxr) 변환의 주파수 모양 비교.

휴대폰 녹음은 크롬이 48 kHz → 16 kHz로 바꾸면서 7 kHz 부근부터 높은 소리를 줄인다.
공개 데이터를 soxr로 바꾸면 이 모양이 다르다. 모델이 "높은 소리가 살짝 줄어듦 = 휴대폰 = 초인종"이라는
지름길을 배울 수 있어서, 두 변환의 차이를 숫자로 잰다.

재는 것
  1) 크롬 변환 특성: PC 크롬 158에 백색 잡음(48 kHz, 44.1 kHz)을 넣고 녹음 페이지와 같은 경로
     (16 kHz AudioContext + AudioWorklet)로 받은 결과 (data/checks/chrome_resampler/*.f32).
     백색 잡음은 모든 주파수 세기가 같으므로, 받은 소리의 스펙트럼이 곧 변환기의 주파수 특성이다.
  2) soxr 변환 특성: 같은 방식의 백색 잡음을 soxr(VHQ)로 바꾼 결과
  3) 실제 소리: 휴대폰 확인 녹음 vs AI Hub 원본을 soxr로 바꾼 것의 평균 스펙트럼 (2~5 kHz에서 맞춤)

사용법
  python train/compare_resample.py
"""

import io
import json
import sys
import wave
import zipfile
from pathlib import Path

import numpy as np
import soxr

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))
from check_wav import load_pyplot, read_wav  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
MEAS = ROOT / "data" / "checks" / "chrome_resampler"
PHONE = ROOT / "data" / "raw" / "other_1126_s01_desk_phone.wav"
FIG = ROOT / "docs" / "figures" / "resample_compare_1127.png"
SR = 16000


def psd(x, n=1024):
    """웰치 방식 평균 파워 스펙트럼 (dB 아님)"""
    w = np.hanning(n)
    hop = n // 2
    frames = np.lib.stride_tricks.sliding_window_view(x, n)[::hop] * w
    p = (np.abs(np.fft.rfft(frames, axis=1)) ** 2).mean(axis=0)
    return np.fft.rfftfreq(n, 1 / SR), p


def response_db(f, p):
    """0.5~5 kHz 평균을 0 dB로 맞춘 주파수 특성"""
    ref = np.mean(p[(f >= 500) & (f <= 5000)])
    return 10 * np.log10(p / ref + 1e-20)


def crossing(f, r, level):
    """특성이 처음으로 level dB 아래로 내려가는 주파수(Hz)"""
    idx = np.where((f > 3000) & (r < level))[0]
    return float(f[idx[0]]) if len(idx) else float("nan")


def summary(name, f, r):
    pts = {k: float(np.interp(k, f, r)) for k in [6000, 6500, 7000, 7500, 7800]}
    print(f"{name:22s} -1dB {crossing(f, r, -1):6.0f} Hz  -3dB {crossing(f, r, -3):6.0f} Hz  -6dB {crossing(f, r, -6):6.0f} Hz  "
          + "  ".join(f"{k / 1000:.1f}k {v:6.1f}" for k, v in pts.items()))
    return pts


def main():
    print("== 1·2) 변환기 주파수 특성 (백색 잡음, 0.5~5 kHz = 0 dB) ==")
    curves = {}
    for rate in [48000, 44100]:
        x = np.fromfile(MEAS / f"chrome_out_{rate}.f32", dtype="<f4").astype(np.float64)
        x = x[SR // 2:]                                    # 처음 0.5초(시작 과도 구간) 뺌
        f, p = psd(x)
        curves[f"크롬 {rate // 1000 if rate == 48000 else 44.1}k→16k"] = (f, response_db(f, p))
        rng = np.random.default_rng(0)
        n = rng.normal(0, 0.2, rate * 11)
        y = soxr.resample(n, rate, SR, quality="VHQ")[SR // 2:]
        f, p = psd(y)
        curves[f"soxr {rate // 1000 if rate == 48000 else 44.1}k→16k"] = (f, response_db(f, p))
    pts = {k: summary(k, *v) for k, v in curves.items()}

    # 3) 실제 소리: 휴대폰 확인 녹음 vs AI Hub(soxr)
    print("\n== 3) 실제 소리 평균 스펙트럼 (2~5 kHz = 0 dB) ==")
    info, pcm = read_wav(PHONE)
    phone = pcm[:, 0] / 32768.0
    f, p = psd(phone)
    ref = np.mean(p[(f >= 2000) & (f <= 5000)])
    real = {"휴대폰 확인 녹음 (크롬 변환)": 10 * np.log10(p / ref + 1e-20)}
    cfg = json.loads((ROOT / "train" / "config.json").read_text(encoding="utf-8"))
    zroot = Path(cfg["paths"]["aihub_zip_root"]).expanduser()
    import csv
    rows = list(csv.DictReader(open(ROOT / "data" / "raw_public" / "aihub" / "index.csv", encoding="utf-8")))
    sys.path.insert(0, str(ROOT / "train"))
    from aihub import real_name
    picks = {}
    for r in rows:
        if r["cls"] in ("siren", "horn") and r["sample_rate"] == "44100" and float(r["seg_sec"]) > 5 and r["cls"] not in picks:
            picks[r["cls"]] = r
    for cls, r in picks.items():
        z = zipfile.ZipFile(zroot / r["zip"])
        info_ = {real_name(i): i for i in z.infolist()}[r["member"]]
        w = wave.open(io.BytesIO(z.read(info_)))
        a = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").reshape(-1, w.getnchannels()).mean(axis=1) / 32768.0
        y = soxr.resample(a, w.getframerate(), SR, quality="VHQ")
        f, p = psd(y)
        ref = np.mean(p[(f >= 2000) & (f <= 5000)])
        real[f"AI Hub {cls} (soxr)"] = 10 * np.log10(p / ref + 1e-20)
        print(f"  AI Hub {cls}: {r['member']} ({w.getframerate()} Hz, {len(a) / w.getframerate():.1f}초)")
    for k, v in real.items():
        print(f"  {k:28s} " + "  ".join(f"{q / 1000:.1f}k {np.interp(q, f, v):6.1f}" for q in [6000, 7000, 7500, 7800]))

    # 그림
    plt = load_pyplot()
    fig, ax = plt.subplots(1, 3, figsize=(15, 4.6), gridspec_kw={"width_ratios": [1.2, 1, 1.2]})
    style = {"크롬 48k→16k": ("#c62828", "-"), "크롬 44.1k→16k": ("#ef9a9a", "--"),
             "soxr 48k→16k": ("#1f5fbf", "-"), "soxr 44.1k→16k": ("#90caf9", "--")}
    for k, (f, r) in curves.items():
        for a in ax[:2]:
            a.plot(f / 1000, r, color=style[k][0], ls=style[k][1], lw=1.4, label=k)
    ax[0].set_xlim(0, 8); ax[0].set_ylim(-60, 5); ax[0].set_title("변환기 주파수 특성 (백색 잡음)")
    ax[1].set_xlim(5, 8); ax[1].set_ylim(-30, 3); ax[1].set_title("확대: 5~8 kHz")
    for a in ax[:2]:
        a.axhline(-3, color="#5d6670", lw=0.6, ls=":"); a.grid(alpha=0.3)
        a.set_xlabel("주파수 (kHz)"); a.set_ylabel("세기 (dB, 0.5~5 kHz = 0)")
    ax[0].legend(fontsize=8, loc="lower left")
    colors = ["#c62828", "#1f5fbf", "#2e7d32"]
    for (k, v), c in zip(real.items(), colors):
        ax[2].plot(f / 1000, v, color=c, lw=1.2, label=k)
    ax[2].set_xlim(0, 8); ax[2].set_ylim(-50, 25); ax[2].grid(alpha=0.3)
    ax[2].set_title("실제 소리 평균 스펙트럼"); ax[2].set_xlabel("주파수 (kHz)"); ax[2].set_ylabel("세기 (dB, 2~5 kHz = 0)")
    ax[2].legend(fontsize=8, loc="lower left")
    fig.tight_layout()
    FIG.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG, dpi=120)
    print(f"\n그림: {FIG.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
