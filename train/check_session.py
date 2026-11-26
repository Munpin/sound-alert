"""녹음 회차 확인 (1단계-2).

회차 하나(wav 파일 하나)를 녹음한 직후 돌려서, 다음 회차로 넘어가도 되는지 본다.

확인하는 것
  1) 파일 이름 규칙   클래스_MMDD_sXX_장소_phone.wav (같은 이름 재저장이면 끝에 _t2 …)
  2) 형식            16000 Hz, 모노, 16비트
  3) 클리핑          잘린 샘플 수, 최댓값(dBFS)
  4) 소리 구간 찾기   앞부분 배경(기본 25초)으로 평소 음량을 재고, 그보다 확실히 커진 구간을 찾는다.
                     --expect와 개수가 다르면 크게 경고한다.
                     other(배경만) 파일은 구간을 찾지 않고 길이와 평균 음량만 본다.
  5) 그림            data/checks/<파일이름>.png  (음량 곡선 + 스펙트로그램 + 찾은 구간)
  6) 구간 목록       data/segments/<파일이름>.csv (start,end,label). 구간 사이와 앞 배경은 other
  7) meta.csv        data/meta.csv에 이 파일의 줄이 있는지
  화면에 나온 내용은 data/checks/<파일이름>.txt에도 저장한다.

사용법
  python train/check_session.py data/raw/doorbell_1126_s01_desk_phone.wav --expect 10

주요 옵션
  --bg-seconds 25   앞부분 배경으로 볼 길이(초). 실제 배경은 약 30초인데, 첫 소리를 배경에
                    섞지 않으려고 조금 짧게 잡는다.
  --margin 12       '확실히 커졌다'의 기준: 배경 평소 음량(중앙값)보다 몇 dB 커야 하는지
  --merge-gap       이 시간(초)보다 가까운 구간은 하나로 묶는다. 기본: 초인종 2.0, 노크 1.0
"""

import argparse
import csv
import re
import sys
from datetime import date
from pathlib import Path

import numpy as np

from check_wav import EXPECTED_RATE, HOP, N_FFT, load_pyplot, read_wav, spectrogram_db

ROOT = Path(__file__).resolve().parents[1]
CLASSES = ["doorbell", "knock", "baby_cry", "siren", "horn", "other"]
NAME_RE = re.compile(
    r"^(?P<cls>[a-z_]+?)_(?P<mmdd>\d{4})_s(?P<sess>\d{2})_(?P<place>[a-z0-9]+)_(?P<device>[a-z]+)(?:_t(?P<take>\d+))?\.wav$"
)

# 클래스별 구간 묶기 규칙
#   merge_gap: 이보다 가까운 구간은 하나로 (초인종은 한 번에 약 4초 울림, 노크는 2~3번 두드림이 한 묶음)
#   min_dur  : 이보다 짧은 구간은 버림 (순간 잡음)
#   pad_pre / pad_post: 찾은 구간 앞뒤로 조금 더 붙임 (소리 시작과 울림 끝을 잘라먹지 않게)
RULES = {
    "doorbell": dict(merge_gap=2.0, min_dur=0.15, pad_pre=0.05, pad_post=0.3),
    "knock": dict(merge_gap=1.0, min_dur=0.02, pad_pre=0.05, pad_post=0.2),
}
DEFAULT_RULE = dict(merge_gap=1.0, min_dur=0.1, pad_pre=0.05, pad_post=0.3)

BAND = (150, 7800)  # 음량을 잴 주파수 범위(Hz). 아주 낮은 웅웅거림(차량·책상 진동)은 뺀다.


class Report:
    """화면에 출력하면서 같은 내용을 모아 두었다가 txt로 저장"""

    def __init__(self):
        self.lines = []

    def __call__(self, s=""):
        print(s)
        self.lines.append(s)

    def save(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(self.lines) + "\n", encoding="utf-8")


def parse_name(name):
    """파일 이름 검사. (정보 dict, 문제 목록)"""
    m = NAME_RE.match(name)
    if not m:
        return None, ["규칙 `클래스_MMDD_sXX_장소_phone.wav`에 맞지 않음"]
    d = m.groupdict()
    problems = []
    if d["cls"] not in CLASSES:
        problems.append(f"클래스 '{d['cls']}'는 목록에 없음 ({', '.join(CLASSES)})")
    try:
        date(2026, int(d["mmdd"][:2]), int(d["mmdd"][2:]))
    except ValueError:
        problems.append(f"날짜 '{d['mmdd']}'가 MMDD 형식의 실제 날짜가 아님")
    if d["device"] != "phone":
        problems.append(f"기기 '{d['device']}'는 phone이어야 함")
    if int(d["sess"]) == 0:
        problems.append("회차는 s01부터")
    d["group_id"] = f"phone_{d['mmdd']}_s{d['sess']}"
    return d, problems


def frame_level_db(x, rate):
    """10 ms마다 BAND 범위 음량(dB). 반환: (dB 배열, 프레임 시작 시각, 스펙트로그램 묶음)"""
    db, freqs, times = spectrogram_db(x, rate)
    band = (freqs >= BAND[0]) & (freqs <= BAND[1])
    power = (10 ** (db[band] / 10)).sum(axis=0)
    level = 10 * np.log10(power + 1e-12)
    starts = np.arange(len(level)) * HOP / rate
    return level, starts, (db, freqs, times)


def find_events(level, rate, bg_frames, margin, rule):
    """배경보다 확실히 커진 구간 찾기.

    - 켜짐 기준(on) : 배경 중앙값 + margin, 그리고 배경 상위 5% 값 + 3 dB 중 큰 값
    - 꺼짐 기준(off): on보다 6 dB 낮게 (단, 배경 상위 5% 값보다는 위)
      on을 한 번이라도 넘은 구간을 off 아래로 내려갈 때까지 넓힌다(소리의 앞뒤 울림 포함).
    """
    bg = level[:bg_frames]
    bg_med = float(np.median(bg))
    bg_p95 = float(np.percentile(bg, 95))
    on = max(bg_med + margin, bg_p95 + 3)
    off = max(on - 6, bg_p95)

    above = level >= off
    runs = []
    i, n = 0, len(level)
    while i < n:
        if above[i]:
            j = i
            while j + 1 < n and above[j + 1]:
                j += 1
            if level[i : j + 1].max() >= on:
                runs.append([i, j])
            i = j + 1
        else:
            i += 1

    # 프레임 번호 → 초
    frame_dur = N_FFT / rate
    events = [[a * HOP / rate, b * HOP / rate + frame_dur] for a, b in runs]

    # 가까운 구간 묶기
    merged = []
    for s, e in events:
        if merged and s - merged[-1][1] < rule["merge_gap"]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    merged = [ev for ev in merged if ev[1] - ev[0] >= rule["min_dur"]]
    return merged, dict(bg_med=bg_med, bg_p95=bg_p95, on=on, off=off)


def pad_events(events, dur, rule):
    out = []
    for s, e in events:
        s = max(0.0, s - rule["pad_pre"])
        e = min(dur, e + rule["pad_post"])
        if out and s <= out[-1][1]:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return out


def segments_table(events, dur, label):
    """찾은 구간 + 그 사이(other)로 파일 전체를 덮는 목록"""
    rows, t = [], 0.0
    for s, e in events:
        if s - t > 1e-6:
            rows.append((t, s, "other"))
        rows.append((s, e, label))
        t = e
    if dur - t > 1e-6:
        rows.append((t, dur, "other"))
    return rows


def check_meta(meta_path, file_name, info):
    """meta.csv에 이 파일 줄이 있는지. (상태, 설명)"""
    if not meta_path.exists():
        return False, f"{meta_path} 파일이 없음"
    with open(meta_path, encoding="utf-8-sig", newline="") as f:
        rows = [r for r in csv.DictReader(f) if r.get("file") == file_name]
    if not rows:
        return False, "이 파일의 줄이 없음 → 녹음 페이지 '저장 기록'에서 복사해 붙여 넣기"
    notes = []
    if len(rows) > 1:
        notes.append(f"같은 파일 줄이 {len(rows)}개")
    r = rows[0]
    if info:
        if r.get("class") != info["cls"]:
            notes.append(f"class '{r.get('class')}' ≠ 파일 이름 '{info['cls']}'")
        if r.get("group_id") != info["group_id"]:
            notes.append(f"group_id '{r.get('group_id')}' ≠ 파일 이름 '{info['group_id']}'")
    if notes:
        return False, "줄은 있으나 " + ", ".join(notes)
    return True, f"있음 (group_id {r.get('group_id')}, place {r.get('place')}, background {r.get('background')}, phone_state {r.get('phone_state')})"


def draw(path, title, x, rate, level, starts, spec, bg_end, th, events, label):
    plt = load_pyplot()
    db, freqs, times = spec
    dur = len(x) / rate
    fig, axes = plt.subplots(2, 1, figsize=(12, 7), sharex=True, gridspec_kw={"height_ratios": [1, 1.6]})

    ax = axes[0]
    ax.plot(starts + N_FFT / 2 / rate, level, lw=0.7, color="#1f5fbf", label=f"음량 ({BAND[0]}~{BAND[1]} Hz)")
    ax.axvspan(0, bg_end, color="#9aa3ad", alpha=0.18, label="배경으로 쓴 구간")
    if th:
        ax.axhline(th["on"], color="#c62828", lw=0.9, ls="--", label=f"켜짐 기준 {th['on']:.1f} dB")
        ax.axhline(th["off"], color="#b26a00", lw=0.9, ls=":", label=f"꺼짐 기준 {th['off']:.1f} dB")
        ax.axhline(th["bg_med"], color="#5d6670", lw=0.8, label=f"배경 중앙값 {th['bg_med']:.1f} dB")
    for k, (s, e) in enumerate(events, 1):
        ax.axvspan(s, e, color="#3b8f5a", alpha=0.25)
    ax.set_ylabel("음량 (dB)")
    ax.legend(loc="upper right", fontsize=8, ncol=2)
    ax.set_title(title)
    ax.grid(alpha=0.3)

    ax = axes[1]
    vmax = np.percentile(db, 99.5)
    ax.pcolormesh(times, freqs / 1000, db, shading="auto", cmap="magma", vmin=vmax - 80, vmax=vmax)
    for k, (s, e) in enumerate(events, 1):
        ax.axvline(s, color="#00e676", lw=1.0)
        ax.axvline(e, color="#00e676", lw=1.0, ls="--")
        ax.text((s + e) / 2, 7.4, str(k), color="#00e676", ha="center", fontsize=9, fontweight="bold")
    ax.axvline(bg_end, color="#ffffff", lw=0.8, ls=":")
    ax.set_ylabel("주파수 (kHz)")
    ax.set_xlabel("시간 (초)")
    ax.set_xlim(0, dur)
    ax.set_ylim(0, rate / 2000)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=110)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description="녹음 회차 확인")
    ap.add_argument("wav", type=Path)
    ap.add_argument("--expect", type=int, default=None, help="소리를 낸 횟수 (예: 10)")
    ap.add_argument("--bg-seconds", type=float, default=25.0, help="앞부분 배경으로 볼 길이(초), 기본 25")
    ap.add_argument("--margin", type=float, default=12.0, help="배경 중앙값보다 몇 dB 커야 소리로 볼지, 기본 12")
    ap.add_argument("--merge-gap", type=float, default=None, help="이보다 가까운 구간은 하나로 (초)")
    ap.add_argument("--meta", type=Path, default=ROOT / "data" / "meta.csv")
    ap.add_argument("--out-dir", type=Path, default=ROOT / "data", help="checks/, segments/를 만들 곳")
    args = ap.parse_args()

    out = Report()
    name = args.wav.name
    stem = args.wav.stem
    ok_all = True
    out(f"=== 회차 확인: {name} ===")

    # 1) 파일 이름
    info, problems = parse_name(name)
    if problems:
        ok_all = False
        out(f"[문제] 파일 이름: {'; '.join(problems)}")
    else:
        take = f", 재저장 {info['take']}번째" if info["take"] else ""
        out(f"[통과] 파일 이름: 클래스 {info['cls']}, 날짜 {info['mmdd']}, 회차 s{info['sess']}, "
            f"장소 {info['place']}{take} → group_id {info['group_id']}")
    cls = info["cls"] if info and info["cls"] in CLASSES else "unknown"

    # 2) 형식
    winfo, pcm = read_wav(args.wav)
    mono = pcm[:, 0].astype(np.int32)
    rate = winfo["rate"]
    x = mono.astype(np.float64) / 32768.0
    dur = len(mono) / rate
    fmt_ok = rate == EXPECTED_RATE and winfo["channels"] == 1 and winfo["bits"] == 16
    ok_all &= fmt_ok
    out(f"[{'통과' if fmt_ok else '문제'}] 형식: {rate} Hz, {winfo['channels']}채널, {winfo['bits']}비트, "
        f"길이 {dur:.2f}초 ({len(mono)} 샘플)")

    # 3) 클리핑
    peak = int(np.abs(mono).max()) if len(mono) else 0
    at_limit = int(np.sum((mono >= 32767) | (mono <= -32768)))
    peak_db = 20 * np.log10(max(peak, 1) / 32768)
    clip_ok = at_limit == 0
    ok_all &= clip_ok
    out(f"[{'통과' if clip_ok else '문제'}] 클리핑: 잘린 샘플 {at_limit}개, 최댓값 {peak} / 32768 ({peak_db:.1f} dBFS)")

    # 4) 소리 구간
    level, starts, spec = frame_level_db(x, rate)
    rms_db = 10 * np.log10(np.mean(x ** 2) + 1e-12)
    events, th = [], None
    bg_end = 0.0
    if cls == "other":
        out(f"[정보] 배경 파일: 구간을 찾지 않음. 길이 {dur:.2f}초, 평균 음량 {rms_db:.1f} dBFS, "
            f"10 ms 음량 중앙값 {np.median(level):.1f} dB (상위 5% {np.percentile(level, 95):.1f} dB)")
    else:
        rule = dict(RULES.get(cls, DEFAULT_RULE))
        if args.merge_gap is not None:
            rule["merge_gap"] = args.merge_gap
        bg_end = min(args.bg_seconds, dur * 0.5)
        if bg_end < args.bg_seconds:
            out(f"[경고] 파일이 짧아 배경을 앞 {bg_end:.1f}초만 씀 (요청 {args.bg_seconds:.0f}초)")
        bg_frames = max(1, int(bg_end * rate / HOP))
        raw, th = find_events(level, rate, bg_frames, args.margin, rule)
        events = pad_events(raw, dur, rule)
        out(f"[정보] 배경 앞 {bg_end:.1f}초: 음량 중앙값 {th['bg_med']:.1f} dB, 상위 5% {th['bg_p95']:.1f} dB "
            f"→ 켜짐 기준 {th['on']:.1f} dB, 꺼짐 기준 {th['off']:.1f} dB")
        out(f"[정보] 묶기 규칙({cls}): {rule['merge_gap']}초 안의 소리는 하나로, {rule['min_dur']}초보다 짧으면 버림")
        out("")
        out(f"  번호   시작(초)   끝(초)   길이(초)  최대 음량(배경보다)  앞 구간과 간격(초)")
        prev = None
        for k, (s, e) in enumerate(events, 1):
            i0, i1 = int(s * rate / HOP), max(int(s * rate / HOP) + 1, int(e * rate / HOP))
            top = level[i0:i1].max() - th["bg_med"]
            gap = f"{s - prev:8.1f}" if prev is not None else "       -"
            flag = "  ← 배경 구간 안" if s < bg_end else ""
            out(f"  {k:4d} {s:9.2f} {e:9.2f} {e - s:9.2f}        +{top:5.1f} dB        {gap}{flag}")
            prev = s
        out("")
        in_bg = sum(1 for s, _ in events if s < bg_end)
        if in_bg:
            out(f"[경고] 배경으로 쓴 앞 {bg_end:.1f}초 안에서 소리 {in_bg}개를 찾음. 배경에 큰 소리가 있었는지 확인")
        if args.expect is None:
            out(f"[정보] 찾은 구간: {len(events)}개 (--expect를 주면 개수를 비교)")
        elif len(events) == args.expect:
            out(f"[통과] 찾은 구간 {len(events)}개 = 기대 {args.expect}개")
        else:
            ok_all = False
            bar = "!" * 60
            out(bar)
            out(f"!!  [경고] 찾은 구간 {len(events)}개 ≠ 기대 {args.expect}개")
            out("!!  그림에서 빠진 소리나 잘못 잡은 잡음을 확인하세요.")
            out("!!  소리가 작아서 빠졌으면 --margin을 낮추고(예: 8), 하나가 둘로 나뉘었으면 --merge-gap을 늘리세요.")
            out(bar)

    # 5) 그림
    png = args.out_dir / "checks" / f"{stem}.png"
    count_txt = f"찾은 구간 {len(events)}개" + (f" / 기대 {args.expect}개" if args.expect is not None else "")
    title = f"{name} · {dur:.1f}초 · 최대 {peak_db:.1f} dBFS · 잘림 {at_limit}개" + ("" if cls == "other" else f" · {count_txt}")
    draw(png, title, x, rate, level, starts, spec, bg_end, th, events, cls)
    out(f"[저장] 그림: {png}")

    # 6) 구간 목록
    seg_path = args.out_dir / "segments" / f"{stem}.csv"
    seg_path.parent.mkdir(parents=True, exist_ok=True)
    rows = segments_table(events, dur, cls if cls in CLASSES else "unknown")
    with open(seg_path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["start", "end", "label"])
        for s, e, lab in rows:
            w.writerow([f"{s:.3f}", f"{e:.3f}", lab])
    if cls == "other":
        out(f"[저장] 구간 목록: {seg_path} (파일 전체 other 1줄)")
    else:
        out(f"[저장] 구간 목록: {seg_path} ({len(rows)}줄: {cls} {len(events)}개, 사이 other {len(rows) - len(events)}개)")

    # 7) meta.csv
    meta_ok, meta_msg = check_meta(args.meta, name, info)
    out(f"[{'통과' if meta_ok else '알림'}] meta.csv: {meta_msg}")

    out("")
    out("결과: " + ("모두 통과" if ok_all and meta_ok else "확인할 것이 있음 (위의 [문제]/[경고]/[알림])"))
    log_path = args.out_dir / "checks" / f"{stem}.txt"
    out.save(log_path)
    print(f"(이 출력은 {log_path}에도 저장됨)")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
