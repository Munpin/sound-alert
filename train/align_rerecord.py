"""6. 스피커 재녹음 파일 자르기.

휴대폰 녹음 페이지로 녹음한 파일에서 시작·끝 신호음(1 kHz 0.5초)을 찾아 시각을 맞추고,
재생 파일의 csv대로 2초씩 잘라 data/raw/rerecord/에 저장한다.
두 신호음 사이 시간으로 재생기·휴대폰 시계 차이를 보정한다. 창마다 원본과 음량 곡선(앞뒤 무음 포함)의
일치도와, 창 음량이 바로 앞 무음보다 몇 dB 큰지(snr_db)를 함께 적는다. snr_db가 10 dB보다 작으면
재생 소리가 너무 작았거나 잘못 잘린 것이니 확인한다(위치를 옮기지는 않는다).
묶음 ID와 분할은 원본에서 물려받고, 출처는 rerecord:<원본 파일>로 적는다(build_meta.py가 읽음).

사용법
  python train/align_rerecord.py data/raw/siren_1128_s05_desk_phone.wav --playlist siren_test
  (녹음 파일의 회차 정보는 data/sessions.csv에서 찾는다)
"""

import argparse
import csv
import sys
from pathlib import Path

import numpy as np

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))
from audio_prep import SR, parse_wav, to_phone_16k, write_wav16  # noqa: E402
from make_playlist import TONE_HZ, TONE_SEC, WIN, load_original  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RR = DATA / "raw" / "rerecord"
INDEX = RR / "rerecord_index.csv"
COLS = ["file", "cls", "group_id", "split", "orig_file", "orig_source", "phone_recording", "playlist", "idx", "place",
        "background", "phone_state", "date", "license", "rec_start_sec", "shift_sec", "snr_db", "corr"]


def envelope(y, hop=160, win=400):
    f = np.lib.stride_tricks.sliding_window_view(np.pad(y, (0, win)), win)[::hop]
    e = 10 * np.log10((f ** 2).mean(axis=1) + 1e-10)
    return e - e.mean()


def find_tone(y, after=0.0):
    """after초 뒤에서 1 kHz 성분이 크게 올라가 0.4초 이상 이어지는 첫 시각(초)"""
    hop, n = 160, 512
    frames = np.lib.stride_tricks.sliding_window_view(y, n)[::hop] * np.hanning(n)
    spec = np.abs(np.fft.rfft(frames, axis=1)) ** 2
    k = int(round(TONE_HZ * n / SR))
    band = spec[:, k - 1:k + 2].sum(axis=1)
    total = spec.sum(axis=1) + 1e-12
    ratio = band / total                      # 1 kHz가 전체에서 차지하는 몫
    db = 10 * np.log10(band + 1e-12)
    floor = np.percentile(db, 20)
    on = (ratio > 0.5) & (db > floor + 20)
    need = int(0.4 * SR / hop)
    run = 0
    for i, v in enumerate(on):
        if i * hop / SR < after:
            continue
        run = run + 1 if v else 0
        if run >= need:
            return (i - need + 1) * hop / SR + n / 2 / SR   # 분석 창의 가운데 시각
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("recording", type=Path)
    ap.add_argument("--playlist", required=True, help="data/raw/rerecord/playlists/<이름> (확장자 없이)")
    args = ap.parse_args()
    rec_name = args.recording.name
    x, sr = parse_wav(args.recording.read_bytes())
    assert sr == SR, "녹음 페이지에서 저장한 16 kHz 파일이어야 함"
    y = x[:, 0]
    plist = list(csv.DictReader(open(RR / "playlists" / f"{args.playlist}.csv", encoding="utf-8")))
    sess = {r["file"]: r for r in csv.DictReader(open(DATA / "sessions.csv", encoding="utf-8"))}.get(rec_name)
    if sess is None:
        print(f"[알림] data/sessions.csv에 {rec_name} 줄이 없음 → 장소·배경 칸이 비게 됨")
        sess = {}

    t0 = find_tone(y)
    if t0 is None:
        raise SystemExit("[실패] 시작 신호음(1 kHz)을 찾지 못함")
    end_play = float(plist[0]["end_tone_sec"])
    t1 = find_tone(y, after=t0 + end_play - 2.0)
    if t1 is None:
        raise SystemExit("[실패] 끝 신호음을 찾지 못함 (재생이 끝까지 녹음됐는지 확인)")
    ratio = (t1 - t0) / end_play
    print(f"신호음: 시작 {t0:.3f}초, 끝 {t1:.3f}초 → 시계 차이 {(ratio - 1) * 1e6:+.0f} ppm")
    if abs(ratio - 1) > 0.002:
        raise SystemExit("[실패] 시계 차이가 0.2%를 넘음: 신호음을 잘못 찾았을 수 있음")
    env_rec = envelope(y)
    hop, pad = 160, 0.5
    floor = np.percentile(env_rec, 5)
    out, corrs, snrs = [], [], []
    for p in plist:
        st = t0 + float(p["start_sec"]) * ratio
        i = int(round(st * SR))
        if i < 0 or i + int(WIN * SR) > len(y):
            print(f"  [{p['idx']}] 녹음 범위 밖 — 건너뜀")
            continue
        # 일치도: [무음 0.5초 + 원본 2초 + 무음 0.5초]의 음량 곡선 vs 녹음 같은 자리
        meta_row = {"file": p["meta_file"], "source": p["source"], "win_start": p["meta_win_start"]}
        seg, osr = load_original(meta_row)
        ref_sig = np.concatenate([np.zeros(int(pad * SR)), to_phone_16k(seg, osr)[: int(WIN * SR)], np.zeros(int(pad * SR))])
        ref = envelope(ref_sig)
        j0 = int(round((st - pad) * SR / hop))
        seg_env = env_rec[j0:j0 + len(ref)]
        n = min(len(ref), len(seg_env))
        a_ = np.maximum(ref[:n], ref[:n].max() - 40)
        b_ = np.maximum(seg_env[:n], floor)
        a_, b_ = a_ - a_.mean(), b_ - b_.mean()
        corr = float(np.dot(a_, b_) / (np.linalg.norm(a_) * np.linalg.norm(b_) + 1e-9))
        corrs.append(corr)
        q = y[max(0, i - int(1.5 * SR)):max(0, i - int(0.5 * SR))]          # 창 앞 무음(재생 파일의 2초 간격 중 가운데)
        snr = 10 * np.log10(np.mean(y[i:i + int(WIN * SR)] ** 2) / (np.mean(q ** 2) + 1e-12) + 1e-12) if len(q) else float("nan")
        snrs.append(snr)
        fname = f"{Path(rec_name).stem}_{int(p['idx']):03d}.wav"
        write_wav16(RR / fname, y[i:i + int(WIN * SR)])
        flag = "  ← 창이 앞 무음보다 10 dB 미만: 확인" if snr < 10 else ""
        print(f"  [{int(p['idx']):3d}] {st:8.3f}초 앞 무음 대비 {snr:5.1f} dB, 일치도 {corr:.2f} {p['source']} {Path(p['meta_file']).name}{flag}")
        out.append({"file": fname, "cls": p["cls"], "group_id": p["group_id"], "split": p["split"],
                    "orig_file": p["meta_file"], "orig_source": p["source"], "phone_recording": rec_name,
                    "playlist": args.playlist, "idx": p["idx"], "place": sess.get("place", ""),
                    "background": sess.get("background", ""), "phone_state": sess.get("phone_state", ""),
                    "date": sess.get("date", ""), "license": p["license"], "rec_start_sec": round(st, 3),
                    "shift_sec": round(st - t0 - float(p["start_sec"]), 4), "snr_db": round(snr, 1), "corr": round(corr, 3)})
    old = [r for r in csv.DictReader(open(INDEX, encoding="utf-8"))] if INDEX.exists() else []
    old = [r for r in old if r["phone_recording"] != rec_name]
    with open(INDEX, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        w.writerows(old + out)
    c = np.array(corrs)
    print(f"\n저장 {len(out)} / {len(plist)}개 → data/raw/rerecord/, 목록 {INDEX.relative_to(ROOT)}")
    sn = np.array(snrs)
    print(f"앞 무음 대비: 중앙값 {np.nanmedian(sn):.1f} dB, 최소 {np.nanmin(sn):.1f} dB, 10 dB 미만 {int((sn < 10).sum())}개 / 일치도 중앙값 {np.median(c):.2f}")


if __name__ == "__main__":
    main()
