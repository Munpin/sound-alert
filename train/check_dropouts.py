"""소리 빠짐 진단 json 분석 (web/dropout-test.html, 녹음 페이지가 저장한 json).

  - 마이크가 만든 소리 길이(track.stats totalFrames, 48 kHz) vs 우리 코드가 받은 소리 길이(received, 16 kHz)
  - 크롬 소리 처리 시계(AudioContext ctxTime) vs 벽시계(performance.now)
  두 차이가 시간에 따라 어떻게 쌓였는지(서서히 / 한 번에) 본다.

사용법: python train/check_dropouts.py data/raw/dropout_*.json [--date 1127]
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))
from check_wav import load_pyplot  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
LABEL = {"meter": {"on": "막대 켬", "off": "막대 끔"}, "brightness": {"auto": "밝기 자동", "max": "밝기 최대"},
         "app": {"none": "앱 없음", "youtube": "유튜브"}}


def label(c):
    return " · ".join(LABEL[k][c[k]] for k in ("meter", "brightness", "app"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--date", default="1127")
    args = ap.parse_args()
    plt = load_pyplot()
    plt.rcParams["axes.unicode_minus"] = False
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.2))
    print("# 소리 빠짐 진단 json 분석")
    for f in args.files:
        j = json.loads(f.read_text(encoding="utf-8"))
        c = j.get("conditions") or {}
        name = label(c) if c else f.stem
        st = j["stats"]
        # 1) 마이크가 만든 소리(48 kHz 프레임) − 우리가 받은 소리(16 kHz 샘플), 시작 대비 ms
        mic = np.array([s["totalFrames"] for s in st], float) / 48000
        rec = np.array([s["received"] for s in st], float) / 16000
        tw = (np.array([s["perf"] for s in st]) - st[0]["perf"]) / 1000
        loss = ((mic - mic[0]) - (rec - rec[0])) * 1000
        # 2) 벽시계 − 크롬 처리 시계 (tick: worklet이 보낸 ctxTime, 메인 스레드가 받은 perf)
        tk = j["ticks"]
        tt = (np.array([t["perf"] for t in tk]) - tk[0]["perf"]) / 1000
        ctx = np.array([t["ctxTime"] for t in tk]) - tk[0]["ctxTime"]
        lag = (tt - ctx) * 1000
        # 받은 소리는 50 ms 조각으로 오므로 1) 값은 ±50 ms 흔들림. 큰 계단만 센다
        d = np.diff(loss)
        jumps = [(round(float(tw[i + 1]), 1), round(float(d[i]), 1)) for i in np.where(d > 30)[0]]
        slope = np.polyfit(tt, lag, 1)[0] * 1e3   # ms/초 → ppm은 ×1000
        print(f"\n== {f.name} ({name})")
        print(f"마이크가 만든 소리 − 받은 소리 (끝): {loss[-1]:.0f} ms / {tw[-1]:.0f}초, 30 ms 넘게 한 번에 늘어난 곳 {len(jumps)}번: {jumps[:12]}")
        print(f"벽시계 − 크롬 처리 시계 (끝): {lag[-1]:.0f} ms, 직선 기울기 {slope:.0f} ppm, 1초 사이 최대 변화 {np.abs(np.diff(lag)).max():.0f} ms")
        print(f"크롬 통계: totalFrames = deliveredFrames ({st[-1]['totalFrames'] == st[-1]['deliveredFrames']}), "
              f"마이크 지연 평균 {np.mean([s['latency'] for s in st]):.1f} ms")
        axes[0].plot(tw, loss, label=name, lw=1)
        axes[1].plot(tt, lag, label=name, lw=1)
    axes[0].set_title("마이크가 만든 소리 - 우리 코드가 받은 소리")
    axes[0].set_xlabel("녹음 시작 후 시간 (초)")
    axes[0].set_ylabel("차이 (ms, 클수록 많이 빠짐)")
    axes[1].set_title("벽시계 - 크롬 소리 처리 시계")
    axes[1].set_xlabel("녹음 시작 후 시간 (초)")
    axes[1].set_ylabel("차이 (ms)")
    for a in axes:
        a.grid(alpha=.3)
        a.legend(fontsize=8)
    fig.tight_layout()
    out = ROOT / "docs" / "figures" / f"dropout_lag_{args.date}.png"
    fig.savefig(out, dpi=110)
    print(f"\n그림: {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
