"""재녹음 정렬 시험: 시계 어긋남을 넣은 흉내 녹음으로 align_rerecord.py의 보정을 확인한다.

흉내 녹음 = 재생 파일(48 kHz) → 시계 어긋남(재생 1초가 녹음에서 1 + ppm×10⁻⁶초) → 짧은 울림 →
            0.3배 → 앞 3.3초 무음 → 크롬 모양 16 kHz → 잡음 −55 dBFS
정답 위치 = 3.3 + (재생 파일 안 시작 시각) × (1 + ppm×10⁻⁶)
비교: 고치기 전(신호음을 10 ms 단위로 찾음) vs 고친 뒤(샘플 단위 + 창마다 따라가기)
--drops N: 녹음에서 50 ms(800샘플) 조각을 N번 빼서, 휴대폰 녹음 중 소리가 빠지는 일을 흉내 (11/27 실제 녹음에서 발견)

사용법
  python train/make_playlist.py --split test --cls siren --n 30 --name sim_siren_test
  python train/sim_rerecord.py --playlist siren_test --ppm 40,300,-500,1000 --drops 0,5
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


def simulate(play48, ppm, seed=0, drops=0):
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
    cuts = np.sort(rng.uniform(LEAD + 2, len(z) / SR - 3, drops)) if drops else np.array([])
    for c in cuts[::-1]:                                             # 뒤에서부터 빼야 앞 위치가 안 바뀜
        i = int(c * SR)
        z = np.concatenate([z[:i], z[i + 800:]])
    return z, k, cuts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--playlist", default="sim_siren_test")
    ap.add_argument("--ppm", default="40,300,-500,1000")
    ap.add_argument("--drops", default="0", help="쉼표로 빠진 조각 수 목록")
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
    print(f"{'넣은 ppm':>8s} {'빠짐':>4s} | {'최대 오차(전)':>12s} | {'최대 오차(후)':>12s} {'평균(후)':>9s} {'쓴 창':>5s}")
    with tempfile.TemporaryDirectory() as td:
        for ppm, nd in [(float(v), int(d)) for d in args.drops.split(",") for v in args.ppm.split(",")]:
            z, k, cuts = simulate(play, ppm, drops=nd)
            rec = Path(td) / "siren_1199_s99_desk_phone.wav"
            write_wav16(rec, z)
            truth = LEAD + starts * k
            cuts_rec = []                                            # 빠진 시각 (녹음 기준, 빼기 전 앞쪽 빠짐 반영)
            for n, c in enumerate(cuts):
                cuts_rec.append(c - 0.05 * n)
            for c in cuts:                                           # 빠진 곳 뒤의 창은 50 ms 당겨짐
                truth = np.where(truth > c, truth - 0.05, truth)
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
            idx = np.array([int(o["idx"]) - 1 for o in out])
            err_new = np.abs(got - truth[idx]) * 1000
            print(f"{ppm:+8.0f} {nd:4d} | {err_old.max():10.1f}ms | {err_new.max():10.2f}ms {err_new.mean():7.2f}ms {len(out):3d}/{len(starts)}")
            # 창 안에서 빠졌는지: 정답 = 빠진 시각(녹음 기준)이 [창 시작, 창 끝] 안
            win_s = truth[idx]
            true_in = np.array([any(ws < c < ws + 2.0 for c in cuts_rec) for ws in win_s])
            flag = np.array([o["drop_in_window"] for o in out])
            hit = int(((flag == "1") & true_in).sum())
            near = flag == "near"
            print(f"         창 안 빠짐: 정답 {int(true_in.sum())}개 → '1' {hit}개 (잘못 표시 {int(((flag == '1') & ~true_in).sum())}개), "
                  f"'1'+near로 잡은 정답 {int(((flag == '1') | near)[true_in].sum())}개, near {int(near.sum())}개 (그중 정답 아님 {int((near & ~true_in).sum())}개)")


if __name__ == "__main__":
    main()
