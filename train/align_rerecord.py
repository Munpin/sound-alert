"""6. 스피커 재녹음 파일 자르기.

휴대폰 녹음 페이지로 녹음한 파일에서 시작·끝 신호음(1 kHz 0.5초)을 찾아 시각을 맞추고,
재생 파일의 csv대로 2초씩 잘라 data/raw/rerecord/에 저장한다.

시계 어긋남 보정
  재생기(PC)와 휴대폰의 시계는 조금씩 다르게 간다. 녹음 안에서 [시작 신호음 → 끝 신호음] 길이를
  재생 파일의 같은 길이로 나눈 비율로 창 시작 시각을 늘이거나 줄인다 (재생 파일 t초 → 녹음 t0 + t × 비율).
  신호음 시작은 1 kHz 성분의 크기 곡선(샘플 단위)에서 안정된 크기의 10%를 넘는 순간으로 찾는다.
  (절반 높이로 잡으면 방 울림이 쌓이는 동안 늦게 잡혀 흉내 녹음에서 16.7 ms 늦었음 → 10%로 낮춤)
  (처음엔 10 ms 단위로 찾아서 수 ms짜리 어긋남은 보정하지 못했음 → 2026-11-27 샘플 단위로 고침)

빠진 소리 따라가기 (2026-11-27 첫 실제 재녹음에서 발견)
  휴대폰 녹음 중간에 소리가 40~50 ms씩 빠지는 일이 있었다(위치가 한 번에 당겨짐). 그러면 앞뒤 신호음
  비율로 고르게 늘이는 보정은 맞지 않는다. 그래서 창마다 재생 파일과 녹음의 음량 곡선(5 ms 간격)을
  [앞 무음 0.5초 + 창 2초 + 뒤 무음 0.5초]로 맞춰 보고, 바로 앞 창 위치에서 ±120 ms 안에서만 찾는다
  (앞뒤 무음 덕분에 일정한 사이렌도 시작·끝 모서리로 위치가 잡힘. 예전처럼 넓게 찾으면 잘못 옮겨졌음).
  일치도가 0.6보다 낮으면 위치를 옮기지 않는다.
  음량 곡선 맞추기는 방 울림 때문에 창마다 수 ms씩 흔들리므로, '어디서 빠졌는지'를 찾는 데만 쓴다:
  20 ms 넘게 달라진 상태가 두 창 이어지면 그 자리에서 빠진 것으로 보고, 빠진 양은 그 구간 창들의
  가운데값으로 잰다. 첫 구간은 시작 신호음 위치를 그대로 쓴다(샘플 단위). 단, 첫 구간부터 20 ms 넘게
  어긋나 있으면(시작 신호음 도중에 소리가 빠진 경우, horn_1127_s02) 맞춰 본 위치를 그대로 쓴다.
  창 음량이 무음 구간보다 10 dB 미만이거나 일치도가 0.6 미만이면 그 창은 쓰지 않는다(다시 녹음하지 않음).
  무음 구간 음량 = 그 녹음의 모든 창 앞 무음(창 시작 1.5~0.5초 전) 음량의 가운데값. 바로 앞 무음 하나만 보면
  그때 난 생활 소음 때문에 멀쩡한 창이 빠졌음(11/27).

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


def track(y, t0, plist, playlist, hop=80, search=0.12, min_corr=0.6):
    """창마다 재생 파일과 녹음의 음량 곡선을 맞춰 위치 차이(초)를 찾는다. 앞 창 위치에서 ±search 안에서만.
    반환: [(위치 차이 초, 일치도, 옮겼는지)]"""
    def env5(v):
        f = np.lib.stride_tricks.sliding_window_view(np.pad(v, (0, 320)), 320)[::hop]
        return 10 * np.log10((f ** 2).mean(axis=1) + 1e-10)
    play, psr = parse_wav((RR / "playlists" / f"{playlist}.wav").read_bytes())
    ep, er = env5(to_phone_16k(play[:, 0], psr)), env5(y)
    floor = np.percentile(er, 5)
    lag, out = 0.0, []
    for p in plist:
        s = float(p["start_sec"])
        a0 = int(round((s - 0.5) * SR / hop))
        a = ep[a0:a0 + int(3.0 * SR / hop)]
        a = np.maximum(a, a.max() - 40)
        a = a - a.mean()
        best = (-1.0, lag)
        for L in range(-int(search * SR / hop), int(search * SR / hop) + 1):
            cand = lag + L * hop / SR
            j = int(round((t0 + s - 0.5 + cand) * SR / hop))
            b = er[j:j + len(a)] if j >= 0 else np.array([])
            if len(b) < len(a):
                continue
            b = np.maximum(b, floor)
            b = b - b.mean()
            c = float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))
            if c > best[0]:
                best = (c, cand)
        moved = best[0] >= min_corr
        if moved:
            lag = best[1]
        out.append((lag, best[0], moved))
    return out


def step_levels(raw, thr=0.02):
    """track() 결과 → 계단 모양 위치 차이. 반환: (창마다 위치 차이 초, 새 구간이 시작한 창 번호들)"""
    v = np.array([lg for lg, _, _ in raw])
    ok = np.array([m for _, _, m in raw])
    seg = np.zeros(len(v), dtype=int)
    cuts, start = [], 0

    def level(a, b):
        w = v[a:b][ok[a:b]]
        return float(np.median(w)) if len(w) else float(np.median(v[a:b]))
    k = 1
    while k < len(v):
        cur = level(start, k)
        if abs(v[k] - cur) > thr and k + 1 < len(v) and abs(v[k + 1] - cur) > thr:
            cuts.append(k)
            start = k
        seg[k] = len(cuts)
        k += 1
    bounds = [0] + cuts + [len(v)]
    lv = [level(bounds[i], bounds[i + 1]) for i in range(len(bounds) - 1)]
    base = lv[0] if abs(lv[0]) > thr else 0.0      # 첫 구간부터 크게 어긋나면 신호음 위치를 믿지 않음
    if base:
        print(f"  [알림] 첫 창들부터 시작 신호음 기준 {lv[0] * 1000:+.0f} ms 어긋남 → 맞춰 본 위치를 씀")
    return [lv[seg[k]] - lv[0] + base for k in range(len(v))], cuts


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
    if abs(ratio - 1) > 0.005:
        raise SystemExit("[실패] 시계 차이가 0.5%를 넘음: 신호음을 잘못 찾았을 수 있음")
    raw = track(y, t0, plist, playlist)
    steps, cuts = step_levels(raw)
    lags = [(st_, c, m) for st_, (_, c, m) in zip(steps, raw)]
    print(f"따라가기: 소리가 빠진 곳 {len(cuts)}번 (창 번호 {[int(plist[k]['idx']) for k in cuts]}), "
          f"마지막 창은 시작 신호음 기준 {steps[-1] * 1000:+.1f} ms (끝 신호음 쪽 차이 {(t1 - t0 - end_play) * 1000:+.1f} ms)")
    env_rec = envelope(y)
    hop, pad = 160, 0.5
    floor = np.percentile(env_rec, 5)
    gaps = []
    for p, (lag, _, _) in zip(plist, lags):
        i = int(round((t0 + float(p["start_sec"]) + lag) * SR))
        q = y[max(0, i - int(1.5 * SR)):max(0, i - int(0.5 * SR))]
        if len(q):
            gaps.append(np.mean(q ** 2))
    noise = float(np.median(gaps))
    print(f"무음 구간 음량(가운데값): {10 * np.log10(noise + 1e-12):.1f} dBFS")
    out, corrs, snrs, dropped = [], [], [], []
    for p, (lag, lcorr, moved) in zip(plist, lags):
        st = t0 + float(p["start_sec"]) + lag
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
        snr = 10 * np.log10(np.mean(y[i:i + int(WIN * SR)] ** 2) / (noise + 1e-12) + 1e-12)   # 무음 구간 가운데값 대비
        snrs.append(snr)
        fname = f"{Path(rec_name).stem}_{int(p['idx']):03d}.wav"
        bad = snr < 10 or corr < 0.6
        if bad:
            dropped.append(int(p["idx"]))
        elif write:
            write_wav16(RR / fname, y[i:i + int(WIN * SR)])
        flag = f"  ← 뺌 (무음 대비 {snr:.1f} dB, 일치도 {corr:.2f})" if bad else ""
        print(f"  [{int(p['idx']):3d}] {st:9.4f}초 무음 대비 {snr:5.1f} dB, 일치도 {corr:.2f} {p['source']} {Path(p['meta_file']).name}{flag}")
        if bad:
            continue
        out.append({"file": fname, "cls": p["cls"], "group_id": p["group_id"], "split": p["split"],
                    "orig_file": p["meta_file"], "orig_source": p["source"], "phone_recording": rec_name,
                    "playlist": playlist, "idx": p["idx"], "place": sess.get("place", ""),
                    "background": sess.get("background", ""), "phone_state": sess.get("phone_state", ""),
                    "date": sess.get("date", ""), "license": p["license"], "rec_start_sec": round(st, 4),
                    "shift_sec": round(lag, 4), "snr_db": round(snr, 1), "corr": round(corr, 3)})
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
    print(f"뺀 창 {len(dropped)}개: {dropped}")
    print(f"무음 대비: 중앙값 {np.nanmedian(sn):.1f} dB, 최소 {np.nanmin(sn):.1f} dB, 10 dB 미만 {int((sn < 10).sum())}개 / 일치도 중앙값 {np.median(c):.2f}")
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
