"""재녹음 정렬 시험: 시계 어긋남을 넣은 흉내 녹음으로 align_rerecord.py의 보정을 확인한다.

흉내 녹음 = 재생 파일(48 kHz) → 시계 어긋남(재생 1초가 녹음에서 1 + ppm×10⁻⁶초) → 짧은 울림 →
            0.3배 → 앞 3.3초 무음 → 크롬 모양 16 kHz → 잡음 −55 dBFS
정답 위치 = 3.3 + (재생 파일 안 시작 시각) × (1 + ppm×10⁻⁶)
비교: 고치기 전(신호음을 10 ms 단위로 찾음) vs 고친 뒤(샘플 단위)

사용법
  python train/make_playlist.py --split test --cls siren --n 30 --name sim_siren_test
  python train/sim_rerecord.py --playlist sim_siren_test --ppm 40,300,-500,1000
"""

import argparse
import contextlib
import io
import sys
import tempfile
from pathlib import Path

import numpy as np
import soxr

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))
import aihub  # noqa: E402,F401  (stdout을 잠시 돌릴 때 import가 다시 일어나지 않게 미리)
import align_rerecord as ar  # noqa: E402
from audio_prep import SR, parse_wav, to_phone_16k, write_wav16  # noqa: E402

LEAD = 3.3


def simulate(play48, ppm, seed=0):
    rng = np.random.default_rng(seed)
    k = 1 + ppm * 1e-6
    y = soxr.resample(play48, 48000, 48000 * k, quality="VHQ")     # 재생 1초 → 녹음 k초
    n = int(0.15 * 48000)
    ir = rng.standard_normal(n) * np.exp(-np.arange(n) / (0.03 * 48000)) * 0.05
    ir[0] = 1.0                                                      # 직접음 + 작은 울림 꼬리
    y = np.convolve(y, ir)[: len(y)] * 0.3
    y = np.concatenate([np.zeros(int(LEAD * 48000)), y, np.zeros(48000)])
    z = to_phone_16k(y, 48000)
    z = z + rng.standard_normal(len(z)) * 10 ** (-55 / 20)
    return z, k


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--playlist", default="sim_siren_test")
    ap.add_argument("--ppm", default="40,300,-500,1000")
    args = ap.parse_args()
    x, sr = parse_wav((ar.RR / "playlists" / f"{args.playlist}.wav").read_bytes())
    assert sr == 48000
    play = x[:, 0]
    import csv
    plist = list(csv.DictReader(open(ar.RR / "playlists" / f"{args.playlist}.csv", encoding="utf-8")))
    starts = np.array([float(p["start_sec"]) for p in plist])
    end_play = float(plist[0]["end_tone_sec"])
    print(f"# 재녹음 정렬 시험 (흉내 녹음, 재생 파일 {args.playlist}: 창 {len(plist)}개, 신호음 간격 {end_play:.1f}초)")
    print("ppm = 재생 1초가 녹음에서 1 + ppm×10⁻⁶초. 끝 신호음에서 어긋남 = 간격 × ppm×10⁻⁶")
    print(f"{'넣은 ppm':>8s} {'끝 어긋남':>9s} | {'잰 ppm(전)':>10s} {'최대 오차(전)':>12s} | {'잰 ppm(후)':>10s} {'최대 오차(후)':>12s} {'평균(후)':>9s}")
    with tempfile.TemporaryDirectory() as td:
        for ppm in [float(v) for v in args.ppm.split(",")]:
            z, k = simulate(play, ppm)
            rec = Path(td) / "siren_1199_s99_desk_phone.wav"
            write_wav16(rec, z)
            truth = LEAD + starts * k
            # 고치기 전: 10 ms 단위 신호음
            y = parse_wav(rec.read_bytes())[0][:, 0]
            c0 = ar.find_tone(y)
            c1 = ar.find_tone(y, after=c0 + end_play - 2.0)
            r_old = (c1 - c0) / end_play
            err_old = np.abs(c0 + starts * r_old - truth) * 1000
            # 고친 뒤
            with contextlib.redirect_stdout(io.StringIO()):
                out, t0, t1, r_new = ar.align(rec, args.playlist, write=False)
            got = np.array([o["rec_start_sec"] for o in out])
            err_new = np.abs(got - truth[: len(got)]) * 1000
            print(f"{ppm:+8.0f} {end_play * ppm * 1e-3:+7.1f}ms | {(r_old - 1) * 1e6:+10.0f} {err_old.max():10.1f}ms | "
                  f"{(r_new - 1) * 1e6:+10.0f} {err_new.max():10.2f}ms {err_new.mean():7.2f}ms")


if __name__ == "__main__":
    main()
