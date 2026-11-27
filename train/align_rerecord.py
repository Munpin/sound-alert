"""6. 스피커 재녹음 파일 자르기.

휴대폰 녹음 페이지로 녹음한 파일에서 시작·끝 신호음(1 kHz 0.5초)을 찾아 시각을 맞추고,
재생 파일의 csv대로 2초씩 잘라 data/raw/rerecord/에 저장한다.

시계 어긋남 보정
  재생기(PC)와 휴대폰의 시계는 조금씩 다르게 간다. 녹음 안에서 [시작 신호음 → 끝 신호음] 길이를
  재생 파일의 같은 길이로 나눈 비율로 창 시작 시각을 늘이거나 줄인다 (재생 파일 t초 → 녹음 t0 + t × 비율).
  신호음 시작은 1 kHz 성분의 크기 곡선(샘플 단위)에서 안정된 크기의 10%를 넘는 순간으로 찾는다.
  (절반 높이로 잡으면 방 울림이 쌓이는 동안 늦게 잡혀 흉내 녹음에서 16.7 ms 늦었음 → 10%로 낮춤)
  (처음엔 10 ms 단위로 찾아서 수 ms짜리 어긋남은 보정하지 못했음 → 2026-11-27 샘플 단위로 고침)

창마다 원본과 음량 곡선(앞뒤 무음 포함)의 일치도와, 창 음량이 바로 앞 무음보다 몇 dB 큰지(snr_db)를
함께 적는다. snr_db가 10 dB보다 작으면 재생 소리가 너무 작았거나 잘못 잘린 것이니 확인한다(위치를 옮기지는 않는다).
묶음 ID와 분할은 원본에서 물려받고, 출처는 rerecord:<원본 파일>로 적는다(build_meta.py가 읽음).

사용법
  python train/align_rerecord.py data/raw/siren_1128_s05_desk_phone.wav --playlist siren_test
  (녹음 파일의 회차 정보는 data/sessions.csv에서 찾는다)
  --dry-run: 파일과 목록을 쓰지 않고 위치만 계산 (시험용)
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
    """after초 뒤에서 1 kHz 성분이 크게 올라가 0.4초 이상 이어지는 첫 시각(초, 10 ms 단위 대략값)"""
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


def tone_envelope(y):
    """1 kHz 성분의 크기 곡선 (샘플 단위). 1 kHz로 내려 곱한 뒤 1주기(16샘플) 평균 → 2 kHz 성분이 지워짐"""
    n = np.arange(len(y))
    z = y * np.exp(-2j * np.pi * TONE_HZ * n / SR)
    k = int(round(SR / TONE_HZ))
    return np.abs(np.convolve(z, np.ones(k) / k, mode="same")) * 2


RISE = 0.1   # 안정된 크기의 몇 배를 넘는 순간을 시작으로 볼지


def half_rise(env, i0, i1, plateau):
    """env[i0:i1]에서 plateau × RISE를 처음 넘는 위치(샘플, 소수점까지)"""
    h = plateau * RISE
    idx = np.where(env[i0:i1] >= h)[0]
    if not len(idx) or idx[0] == 0:
        return None
    j = i0 + idx[0]
    a, b = env[j - 1], env[j]
    return j - 1 + (h - a) / (b - a)


def _ref_offset():
    """재생 파일과 같은 신호음(10 ms 켜기)에서 실제 시작과 RISE 높이 위치의 차이(초)"""
    t = np.arange(int(TONE_SEC * SR)) / SR
    tone = 0.5 * np.sin(2 * np.pi * TONE_HZ * t)
    f = int(0.01 * SR)
    tone[:f] *= np.linspace(0, 1, f)
    tone[-f:] *= np.linspace(1, 0, f)
    y = np.concatenate([np.zeros(SR), tone, np.zeros(SR)])
    env = tone_envelope(y)
    plateau = np.median(env[SR + int(0.1 * SR):SR + int(0.35 * SR)])
    return half_rise(env, SR - 160, SR + 800, plateau) / SR - 1.0


REF_OFFSET = _ref_offset()


def find_tone_fine(env, coarse):
    """대략 위치(coarse) 주변에서 신호음 시작을 샘플 단위로 다시 찾는다(초)"""
    c = int(round(coarse * SR))
    plateau = np.median(env[c + int(0.1 * SR):c + int(0.35 * SR)])
    pos = half_rise(env, max(1, c - int(0.06 * SR)), c + int(0.1 * SR), plateau)
    if pos is None:
        print("  [알림] 신호음 시작을 정밀하게 찾지 못해 대략값(10 ms 단위)을 씀")
        return coarse
    return pos / SR - REF_OFFSET


def align(recording, playlist, write=True):
    """반환: (창 목록, 시작 신호음 초, 끝 신호음 초, 시계 비율)"""
    rec_name = recording.name
    x, sr = parse_wav(recording.read_bytes())
    assert sr == SR, "녹음 페이지에서 저장한 16 kHz 파일이어야 함"
    y = x[:, 0]
    plist = list(csv.DictReader(open(RR / "playlists" / f"{playlist}.csv", encoding="utf-8")))
    sess = {r["file"]: r for r in csv.DictReader(open(DATA / "sessions.csv", encoding="utf-8"))}.get(rec_name)
    if sess is None:
        print(f"[알림] data/sessions.csv에 {rec_name} 줄이 없음 → 장소·배경 칸이 비게 됨")
        sess = {}

    c0 = find_tone(y)
    if c0 is None:
        raise SystemExit("[실패] 시작 신호음(1 kHz)을 찾지 못함")
    end_play = float(plist[0]["end_tone_sec"])
    c1 = find_tone(y, after=c0 + end_play - 2.0)
    if c1 is None:
        raise SystemExit("[실패] 끝 신호음을 찾지 못함 (재생이 끝까지 녹음됐는지 확인)")
    tenv = tone_envelope(y)
    t0, t1 = find_tone_fine(tenv, c0), find_tone_fine(tenv, c1)
    ratio = (t1 - t0) / end_play       # 재생 파일 1초가 녹음에서 몇 초인지
    print(f"신호음: 시작 {t0:.4f}초, 끝 {t1:.4f}초 (재생 파일에서는 {end_play:.4f}초 간격) "
          f"→ 시계 차이 {(ratio - 1) * 1e6:+.0f} ppm, 끝 쪽 보정 {(t1 - t0 - end_play) * 1000:+.1f} ms")
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
        if write:
            write_wav16(RR / fname, y[i:i + int(WIN * SR)])
        flag = "  ← 창이 앞 무음보다 10 dB 미만: 확인" if snr < 10 else ""
        print(f"  [{int(p['idx']):3d}] {st:9.4f}초 앞 무음 대비 {snr:5.1f} dB, 일치도 {corr:.2f} {p['source']} {Path(p['meta_file']).name}{flag}")
        out.append({"file": fname, "cls": p["cls"], "group_id": p["group_id"], "split": p["split"],
                    "orig_file": p["meta_file"], "orig_source": p["source"], "phone_recording": rec_name,
                    "playlist": playlist, "idx": p["idx"], "place": sess.get("place", ""),
                    "background": sess.get("background", ""), "phone_state": sess.get("phone_state", ""),
                    "date": sess.get("date", ""), "license": p["license"], "rec_start_sec": round(st, 4),
                    "shift_sec": round(st - t0 - float(p["start_sec"]), 4), "snr_db": round(snr, 1), "corr": round(corr, 3)})
    if write:
        old = [r for r in csv.DictReader(open(INDEX, encoding="utf-8"))] if INDEX.exists() else []
        old = [r for r in old if r["phone_recording"] != rec_name]
        with open(INDEX, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=COLS)
            w.writeheader()
            w.writerows(old + out)
        print(f"\n저장 {len(out)} / {len(plist)}개 → data/raw/rerecord/, 목록 {INDEX.relative_to(ROOT)}")
    else:
        print(f"\n[dry-run] 계산 {len(out)} / {len(plist)}개 (파일·목록은 쓰지 않음)")
    c = np.array(corrs)
    sn = np.array(snrs)
    print(f"앞 무음 대비: 중앙값 {np.nanmedian(sn):.1f} dB, 최소 {np.nanmin(sn):.1f} dB, 10 dB 미만 {int((sn < 10).sum())}개 / 일치도 중앙값 {np.median(c):.2f}")
    return out, t0, t1, ratio


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("recording", type=Path)
    ap.add_argument("--playlist", required=True, help="data/raw/rerecord/playlists/<이름> (확장자 없이)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    align(args.recording, args.playlist, write=not args.dry_run)


if __name__ == "__main__":
    main()
