"""3. CryCeleb2023 (아기 울음 학습용): 받은 데이터 정리.

사용법
  python train/cryceleb.py summary   # 파일 수, 길이 분포, 샘플레이트, 메타데이터, 대역폭 → 화면 + 그림
  python train/cryceleb.py windows   # 아기 ID 단위 분할 + 2초 창 → wav16k/, orig2s/, windows.csv

2초 창 (사용자 결정 2026-11-27)
  - CryCeleb의 train·dev 부분만 쓴다. test 부분은 같은 아기의 출생·퇴원 녹음에 다른 익명 ID가 붙어 묶을 수 없다
  - 같은 녹음(아기 + 출생 B/퇴원 D)의 조각을 순서대로 이어 붙인다. 사이 간격 0.2~0.4초(숨 들이쉬기 흉내)
  - 간격은 디지털 무음 대신 아주 작은 잡음(그 녹음 20 ms 프레임 RMS 아래 5% 크기)으로 채운다
  - 이어 붙인 소리를 겹치지 않게 2초씩 자른다
  - 분할: 아기 ID 단위 70/15/15. 상한 학습 600, 검증·시험 각 150 (아기를 돌아가며 하나씩)

입력: data/raw_public/cryceleb/metadata.csv, audio/ (audio.zip을 푼 것)
그림: docs/figures/cryceleb_durations_<MMDD>.png
대역폭 = 평균 스펙트럼이 1~3 kHz 평균보다 50 dB 넘게 작아지기 시작하는 주파수 (AudioSet 검사와 같은 정의)
         녹음(아기 + 출생 B/퇴원 D) 하나의 모든 조각을 합쳐 잰다. 원본 16 kHz 파일 기준.
"""

import collections
import csv
import json
import random
import struct
import sys
from pathlib import Path

import numpy as np

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))
from audio_prep import parse_wav, to_phone_16k, write_wav16  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "data" / "raw_public" / "cryceleb"
CFG = json.loads((ROOT / "train" / "config.json").read_text(encoding="utf-8"))


def header(p):
    b = p.read_bytes()[:64]
    i = b.find(b"fmt ")
    fmt, ch, sr, _, _, bits = struct.unpack("<HHIIHH", b[i + 8:i + 24])
    return fmt, ch, sr, bits


def bandwidth(xs, sr):
    n = 512
    acc, cnt = np.zeros(n // 2 + 1), 0
    for x in xs:
        if len(x) < n:
            continue
        f = np.lib.stride_tricks.sliding_window_view(x, n)[::256] * np.hanning(n)
        acc += (np.abs(np.fft.rfft(f, axis=1)) ** 2).sum(axis=0)
        cnt += len(f)
    if not cnt:
        return None
    db = 10 * np.log10(acc / cnt + 1e-20)
    fr = np.fft.rfftfreq(n, 1 / sr)
    ref = db[(fr >= 1000) & (fr <= 3000)].mean()
    above = np.where((fr > 3000) & (db < ref - 50))[0]
    return fr[above[0]] / 1000 if len(above) else sr / 2000


def cmd_summary(date="1127"):
    rows = list(csv.DictReader(open(D / "metadata.csv", encoding="utf-8")))
    dur = np.array([float(r["duration"]) for r in rows])
    print(f"# CryCeleb2023 정리 (data/raw_public/cryceleb/metadata.csv, audio/)")
    print(f"파일 {len(rows)}개, 아기 {len({r['baby_id'] for r in rows})}명, 합계 {dur.sum() / 3600:.2f}시간")
    for sp in ("train", "dev", "test"):
        rs = [r for r in rows if r["split"] == sp]
        print(f"  {sp:5s} 파일 {len(rs):5d}개, 아기 {len({r['baby_id'] for r in rs}):3d}명")
    print(f"녹음 시점: {dict(collections.Counter(r['period'] for r in rows))} (B = 출생 직후, D = 퇴원 때)")

    # 실제 파일 확인
    missing, heads = 0, collections.Counter()
    for r in rows:
        p = D / r["file_name"]
        if not p.exists():
            missing += 1
            continue
        heads[header(p)] += 1
    print(f"wav 없음 {missing}개")
    print("형식(포맷, 채널, 샘플레이트, 비트): " + ", ".join(f"{k} {v}개" for k, v in heads.items()))

    q = np.percentile(dur, [0, 10, 25, 50, 75, 90, 100])
    print("\n## 조각 길이 (초)")
    print("최소 {:.2f} / 10% {:.2f} / 25% {:.2f} / 중앙값 {:.2f} / 75% {:.2f} / 90% {:.2f} / 최대 {:.2f}".format(*q))
    for t in (0.5, 1.0, 1.5, 2.0):
        print(f"  {t:.1f}초 이상: {(dur >= t).sum():5d}개 ({(dur >= t).mean() * 100:.1f}%)")

    # 녹음(아기 + 시점) 단위
    rec = collections.defaultdict(list)
    for r in rows:
        rec[(r["baby_id"], r["period"])].append(r)
    nseg = np.array([len(v) for v in rec.values()])
    tot = np.array([sum(float(r["duration"]) for r in v) for v in rec.values()])
    print(f"\n## 녹음(아기 + 시점) {len(rec)}개")
    print("녹음 하나의 조각 수: 최소 {} / 중앙값 {:.0f} / 최대 {}".format(nseg.min(), np.median(nseg), nseg.max()))
    print("녹음 하나의 울음 합계(초): 최소 {:.1f} / 중앙값 {:.1f} / 최대 {:.1f}".format(tot.min(), np.median(tot), tot.max()))
    print(f"  울음 합계 2초 미만 녹음: {(tot < 2).sum()}개")
    print("메타데이터에 조각 사이 간격(원래 녹음 안의 시각)은 없음 → 순서(chronological_index)만 있음")

    # 대역폭
    bws = []
    for (b, per), v in sorted(rec.items()):
        xs = []
        for r in v:
            x, sr = parse_wav((D / r["file_name"]).read_bytes())
            xs.append(x[:, 0])
        bws.append(bandwidth(xs, sr))
    bws = np.array([b for b in bws if b is not None])
    print(f"\n## 대역폭 (녹음 {len(bws)}개)")
    for t in (4, 5, 6, 7, 7.5):
        print(f"  {t} kHz 미만: {(bws < t).sum()}개")
    print("최소 {:.1f} / 10% {:.1f} / 중앙값 {:.1f} kHz".format(bws.min(), np.percentile(bws, 10), np.median(bws)))

    # 그림
    from check_wav import load_pyplot
    plt = load_pyplot()
    fig, ax = plt.subplots(1, 2, figsize=(11, 3.8))
    ax[0].hist(dur, bins=np.arange(0, max(4.0, dur.max()) + 0.1, 0.1), color="#4c72b0")
    ax[0].axvline(2.0, color="r", ls="--", label="2초")
    ax[0].set_xlabel("조각 길이 (초)")
    ax[0].set_ylabel("조각 수 (개)")
    ax[0].set_title(f"울음 조각(숨 내쉬기) 길이, {len(dur)}개")
    ax[0].legend()
    ax[1].hist(tot, bins=40, color="#55a868")
    ax[1].set_xlabel("녹음 하나의 울음 합계 (초)")
    ax[1].set_ylabel("녹음 수 (개)")
    ax[1].set_title(f"녹음(아기 + 출생/퇴원) {len(rec)}개")
    fig.tight_layout()
    out = ROOT / "docs" / "figures" / f"cryceleb_durations_{date}.png"
    fig.savefig(out, dpi=120)
    print(f"\n그림: {out.relative_to(ROOT)}")


def build_stream(v, key):
    """녹음 하나의 조각을 순서대로 이어 붙인다. 사이 간격은 0.2~0.4초, 아주 작은 잡음으로 채움.
    반환: (16 kHz 원본 음질 신호, [(시작 샘플, 끝 샘플, file_id)])"""
    import zlib
    C = CFG["cryceleb"]
    rng = np.random.default_rng([C["seed"], zlib.crc32(key.encode())])
    segs = []
    for r in sorted(v, key=lambda r: r["chronological_index"]):
        x, sr = parse_wav((D / r["file_name"]).read_bytes())
        assert sr == 16000
        segs.append((x[:, 0].copy(), r["file_id"]))
    # 잡음 크기 = 이 녹음 조각들의 20 ms 프레임 RMS 중 아래 5% 값
    fr = np.concatenate([np.sqrt((np.lib.stride_tricks.sliding_window_view(x, 320)[::160] ** 2).mean(axis=1))
                         for x, _ in segs if len(x) >= 320])
    noise_rms = float(np.percentile(fr, C["gap_noise_percentile"]))
    f = 160                                    # 10 ms 부드럽게 켜고 끄기
    ramp = np.linspace(0, 1, f)
    parts, spans, t = [], [], 0
    for k, (x, fid) in enumerate(segs):
        if k:
            g = int(rng.uniform(*C["gap_sec"]) * 16000)
            parts.append(rng.standard_normal(g) * noise_rms)
            t += g
        if len(x) > 2 * f:
            x[:f] = x[:f] * ramp + rng.standard_normal(f) * noise_rms * (1 - ramp)
            x[-f:] = x[-f:] * ramp[::-1] + rng.standard_normal(f) * noise_rms * ramp
        parts.append(x)
        spans.append((t, t + len(x), fid))
        t += len(x)
    return np.concatenate(parts), spans, noise_rms


def assign_babies(babies):
    C = CFG["cryceleb"]
    b = sorted(babies)
    random.Random(C["split_seed"]).shuffle(b)
    n = len(b)
    n_tr = round(n * C["split_ratios"]["train"])
    n_va = round(n * C["split_ratios"]["val"])
    return {x: ("train" if i < n_tr else "val" if i < n_tr + n_va else "test") for i, x in enumerate(b)}


def cmd_windows():
    C = CFG["cryceleb"]
    W = 32000
    rows = [r for r in csv.DictReader(open(D / "metadata.csv", encoding="utf-8")) if r["split"] in C["use_splits"]]
    rec = collections.defaultdict(list)
    for r in rows:
        rec[(r["baby_id"], r["period"])].append(r)
    split_of = assign_babies({r["baby_id"] for r in rows})
    # 1차: 녹음마다 가능한 2초 창(겹치지 않게)과 음량
    cand = collections.defaultdict(lambda: collections.defaultdict(list))   # split → 아기 → [(녹음, k)]
    n_all, n_quiet = collections.Counter(), 0
    for key, v in rec.items():
        y, spans, _ = build_stream(v, f"{key[0]}_{key[1]}")
        for k in range(len(y) // W):
            db = 20 * np.log10(np.sqrt(np.mean(y[k * W:(k + 1) * W] ** 2)) + 1e-12)
            if db < C["min_window_dbfs"]:
                n_quiet += 1
                continue
            sp = split_of[key[0]]
            cand[sp][key[0]].append((key, k))
            n_all[sp] += 1
    # 고르기: 분할마다 아기를 돌아가며 하나씩 (상한까지)
    rng = random.Random(C["seed"])
    chosen = {}
    for sp in ("train", "val", "test"):
        q = []
        for b in sorted(cand[sp]):
            lst = cand[sp][b][:]
            rng.shuffle(lst)
            q.append(lst)
        rng.shuffle(q)
        out = []
        while len(out) < C["caps"][sp] and any(q):
            for lst in q:
                if lst and len(out) < C["caps"][sp]:
                    out.append(lst.pop())
        chosen[sp] = out
    # 2차: 고른 창만 원본 음질(orig2s/)과 휴대폰 모양(wav16k/)으로 저장
    need = collections.defaultdict(list)
    for sp, lst in chosen.items():
        for key, k in lst:
            need[key].append((k, sp))
    (D / "wav16k").mkdir(exist_ok=True)
    (D / "orig2s").mkdir(exist_ok=True)
    out = []
    for key in sorted(need):
        y, spans, nr = build_stream(rec[key], f"{key[0]}_{key[1]}")
        z = to_phone_16k(y, 16000)
        for k, sp in sorted(need[key]):
            a, b = k * W, (k + 1) * W
            used = [fid for s, e, fid in spans if s < b and e > a]
            name = f"cryceleb_{key[0]}_{key[1]}_w{k:02d}.wav"
            write_wav16(D / "orig2s" / name, y[a:b])
            write_wav16(D / "wav16k" / name, z[a:b])
            out.append({"file": name, "cls": "baby_cry", "group_id": f"cryceleb:{key[0]}", "split": sp,
                        "license": "CC BY-NC-ND 4.0 (CryCeleb2023)",
                        "note": f"조각 {used[0]}~{used[-1].rsplit('_', 1)[1]} ({len(used)}개) 이어 붙임, 간격 0.2~0.4초 잡음",
                        "win_start": 0.0, "orig_path": f"orig2s/{name}", "orig_start_sec": 0.0})
    with open(D / "windows.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    nb = collections.Counter(split_of.values())
    print(f"# CryCeleb 2초 창 (train+dev 부분만, 아기 {len(split_of)}명, 녹음 {len(rec)}개)")
    print(f"아기 분할: " + ", ".join(f"{s} {nb[s]}명" for s in ("train", "val", "test")))
    print(f"가능한 창: " + ", ".join(f"{s} {n_all[s]}개" for s in ("train", "val", "test")) + f" / 너무 조용해서 뺀 창 {n_quiet}개")
    for sp in ("train", "val", "test"):
        o = [x for x in out if x["split"] == sp]
        nseg = [int(x["note"].split("(")[1].split("개")[0]) for x in o]
        print(f"  고른 {sp:5s} {len(o):4d}개 (상한 {C['caps'][sp]}), 아기 {len({x['group_id'] for x in o})}명, "
              f"창 하나의 조각 수 중앙값 {np.median(nseg):.0f}")
    print("저장: data/raw_public/cryceleb/wav16k/ (휴대폰 모양), orig2s/ (재녹음용 원본 음질), windows.csv")


if __name__ == "__main__":
    cmds = {"summary": cmd_summary, "windows": cmd_windows}
    if len(sys.argv) < 2 or sys.argv[1] not in cmds:
        print(__doc__)
        sys.exit(1)
    cmds[sys.argv[1]]()
