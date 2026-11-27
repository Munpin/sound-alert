"""8. 모든 출처를 data/meta.csv 하나로 모은다. 한 줄 = 2초 창 하나.

입력
  own       data/sessions.csv(회차 정보) + data/segments/<회차>.csv(소리 구간) + data/raw/<회차>.wav
  rerecord  data/raw/rerecord/rerecord_index.csv (align_rerecord.py가 만든다)
  esc50     data/raw_public/esc50/windows.csv
  aihub     data/raw_public/aihub/windows.csv
  audioset  data/raw_public/audioset/cry_windows.csv (+ config meta.audioset_*)
  cryceleb  data/raw_public/cryceleb/windows.csv (있으면)
  fsd50k    data/raw_public/fsd50k/windows.csv (있으면)

출력
  data/meta.csv  칸: file, class, subclass, source, orig_source, group_id, split, place, background, phone_state, device,
                     date, license, note, win_start
                 file은 data/ 아래 경로, win_start는 그 파일 안에서 2초 창이 시작하는 초
                 subclass: 원래 데이터의 소분류(AI Hub 소분류, ESC-50 category 등). 경적을 차량/이륜차로 나눠 점수를 낼 때 쓴다
                 orig_source: 소리의 원래 출처(재녹음이면 원본의 출처). 아기 울음을 출처별로 나눠 점수를 낼 때 쓴다
                 drop_in_window: 재녹음 창 안에서 휴대폰 녹음 소리가 빠졌는지. 1 = 창 안, near = 빠진 곳 바로 옆 창(확실하지 않음),
                                 0 = 아님, 빈칸 = 재녹음 아님. 빼고 채점하려면 1과 near를 뺀다 (align_rerecord.py)

직접 녹음 → 2초 창
  - 소리 하나에 창 하나: 2초보다 길면 가장 큰 2초, 짧으면 소리를 가운데 두고 앞뒤는 같은 녹음 그대로
  - other: other 구간을 겹치지 않게 2초씩. 소리 끝 1초·시작 0.3초 근처는 쓰지 않는다(울림 꼬리가 섞이지 않게)
  - split은 sessions.csv의 split 칸(비어 있으면 'unassigned')
학습 상한(설계서 4절: other 2,400, siren·horn 각 600): 직접 녹음·재녹음·ESC-50은 모두 넣고,
남은 자리를 나머지 공개 데이터에서 출처·묶음을 돌아가며 채운다.

사용법: python train/build_meta.py
"""

import collections
import csv
import json
import random
import sys
from pathlib import Path

import numpy as np

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))
from audio_prep import SR, best_window, parse_wav  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CFG = json.loads((ROOT / "train" / "config.json").read_text(encoding="utf-8"))
M = CFG["meta"]
COLS = ["file", "class", "subclass", "source", "orig_source", "group_id", "split", "place", "background", "phone_state",
        "device", "date", "license", "note", "win_start", "drop_in_window"]
WIN = 2.0


def rows_csv(path, enc="utf-8"):
    return list(csv.DictReader(open(path, encoding=enc))) if Path(path).exists() else []


def row(**kw):
    r = {c: "" for c in COLS}
    r.update({k: ("" if v is None else v) for k, v in kw.items()})
    return r


# ---------------------------------------------------------------------------
def own_rows():
    out = []
    for s in rows_csv(DATA / "sessions.csv"):
        wav = DATA / "raw" / s["file"]
        seg = DATA / "segments" / (Path(s["file"]).stem + ".csv")
        if not wav.exists() or not seg.exists():
            print(f"  [own] 건너뜀(파일 또는 구간 목록 없음): {s['file']}")
            continue
        x, sr = parse_wav(wav.read_bytes())
        y = x[:, 0]
        dur = len(y) / sr
        segs = rows_csv(seg)
        split = s.get("split") or "unassigned"
        base = dict(source="own", orig_source="own", group_id=s["group_id"], split=split, place=s["place"], background=s["background"],
                    phone_state=s["phone_state"], device=s["device"], date=s["date"], license="own")
        cls_ev = [(float(r["start"]), float(r["end"])) for r in segs if r["label"] != "other"]
        n_cls = 0
        for a, b in cls_ev:
            if b - a >= WIN:
                i, _ = best_window(y[int(a * sr):int(b * sr)], WIN)
                st = a + i / sr
            else:
                st = min(max(0.0, (a + b) / 2 - WIN / 2), dur - WIN)
            out.append(row(file=f"raw/{s['file']}", **{"class": s["class"]}, subclass=s["class"], note="",
                           win_start=round(st, 3), **base))
            n_cls += 1
        # other: 소리 앞뒤 보호 구간을 뺀 other 구간을 2초씩
        bad = [(a - M["own_other_guard_before_sec"], b + M["own_other_guard_after_sec"]) for a, b in cls_ev]
        n_oth = 0
        for r in segs:
            if r["label"] != "other":
                continue
            a, b = float(r["start"]), float(r["end"])
            for ba, bb in bad:            # 보호 구간과 겹치면 줄인다
                if ba < b and bb > a:
                    if ba <= a:
                        a = max(a, bb)
                    else:
                        b = min(b, ba)
            t = a
            while t + WIN <= b + 1e-6:
                out.append(row(file=f"raw/{s['file']}", **{"class": "other"}, subclass=f"own {r['note'] or 'gap'}",
                               note=f"own other ({r['note'] or 'gap'})",
                               win_start=round(t, 3), **base))
                t += WIN
                n_oth += 1
        print(f"  [own] {s['file']}: {s['class']} {n_cls}개, other {n_oth}개, split {split}")
    return out


def rerecord_rows(public):
    """public: 공개 데이터 줄들. 원본 줄에서 subclass를 물려받는다"""
    sub_of = {r["file"]: r["subclass"] for r in public}
    out = []
    for r in rows_csv(DATA / "raw" / "rerecord" / "rerecord_index.csv"):
        out.append(row(file=f"raw/rerecord/{r['file']}", **{"class": r["cls"]}, subclass=sub_of.get(r["orig_file"], ""),
                       source=f"rerecord:{r['orig_file']}", orig_source=r["orig_source"],
                       group_id=r["group_id"], split=r["split"], place=r["place"], background=r["background"],
                       phone_state=r["phone_state"], device="phone", date=r["date"], license=r["license"],
                       note=f"재녹음 원본 {r['orig_source']}", win_start=0.0,
                       drop_in_window=r.get("drop_in_window", "")))
    return out


def esc50_rows():
    return [row(file=f"raw_public/esc50/wav16k/{r['file']}", **{"class": r["cls"]}, subclass=r["category"], source="esc50",
                orig_source="esc50", group_id=r["group_id"], split=r["split"], device="public", license="CC BY-NC 3.0 (ESC-50)",
                note=f"{r['category']}, fold {r['fold']}, 원본 {r['win_start_sec']}초부터", win_start=0.0)
            for r in rows_csv(DATA / "raw_public" / "esc50" / "windows.csv")]


def aihub_rows():
    return [row(file=f"raw_public/aihub/wav16k/{r['file']}", **{"class": r["cls"]}, subclass=r["subcat"], source="aihub",
                orig_source="aihub", group_id=r["group_id"], split=r["split"], place=r["place"], device="public", date=r["date"],
                license="AI Hub 이용약관 (라벨 json: CC 0)", note=f"{r['subcat']}, 조각 안 {r['win_start_sec']}초부터",
                win_start=0.0)
            for r in rows_csv(DATA / "raw_public" / "aihub" / "windows.csv")]


def audioset_rows():
    out, skipped = [], collections.Counter()
    for r in rows_csv(DATA / "raw_public" / "audioset" / "cry_windows.csv", enc="utf-8-sig"):
        if r["ytid"] in M["audioset_exclude_low_band"]:
            skipped["저음질(대역폭 7 kHz 미만)"] += 1
            continue
        if r["ytid"] in M["audioset_drop"]:
            skipped["울음 없음(사용자 판단)"] += 1
            continue
        st = r.get("use_start_sec") or M["audioset_window_fix"].get(r["ytid"]) or r["auto_start_sec"]
        how = "사람이 고름" if (r.get("use_start_sec") or r["ytid"] in M["audioset_window_fix"]) else "자동 후보(가장 큰 2초)"
        out.append(row(file=f"raw_public/audioset/wav16k/{r['file']}", **{"class": "baby_cry"}, subclass="Baby cry, infant cry",
                       source="audioset", orig_source="audioset",
                       group_id=f"audioset:{r['ytid']}", split="test", device="public",
                       license="YouTube (AudioSet 라벨 CC BY 4.0)", note=f"10초 중 창, {how}", win_start=float(st)))
    if skipped:
        print(f"  [audioset] 뺀 것: {dict(skipped)}")
    return out


def generic_rows(name):
    """cryceleb / fsd50k: windows.csv에 file, cls, group_id, split, license, note, win_start가 있다고 가정"""
    out = []
    for r in rows_csv(DATA / "raw_public" / name / "windows.csv"):
        out.append(row(file=f"raw_public/{name}/wav16k/{r['file']}", **{"class": r["cls"]}, subclass=r.get("subclass") or name,
                       source=name, orig_source=name,
                       group_id=r["group_id"], split=r["split"], device="public", license=r.get("license", ""),
                       note=r.get("note", ""), win_start=float(r.get("win_start") or 0)))
    return out


FIRST = ("own", "rerecord", "esc50")   # 상한을 채울 때 먼저 모두 넣는 출처 (휴대폰 경로, 작은 공개 데이터)


def cap_train(rows, cls, cap):
    """학습 cls가 상한을 넘으면: FIRST 출처는 모두, 나머지는 출처→묶음을 돌아가며"""
    oth = [r for r in rows if r["class"] == cls and r["split"] == "train"]
    if len(oth) <= cap:
        return rows, 0
    keep = [r for r in oth if r["source"].split(":")[0] in FIRST]
    rng = random.Random(0)
    by_src = collections.defaultdict(lambda: collections.defaultdict(list))
    for r in oth:
        if r["source"].split(":")[0] not in FIRST:
            by_src[r["source"]][r["group_id"]].append(r)
    queues = {}
    for src, gs in by_src.items():
        gl = list(gs.values())
        for g in gl:
            rng.shuffle(g)
        rng.shuffle(gl)
        queues[src] = gl
    while len(keep) < cap and any(queues.values()):
        for src in sorted(queues):
            gl = queues[src]
            if not gl or len(keep) >= cap:
                continue
            g = gl.pop(0)
            keep.append(g.pop(0))
            if g:
                gl.append(g)
    keep_ids = {id(r) for r in keep}
    dropped = sum(1 for r in oth if id(r) not in keep_ids)
    out = [r for r in rows if not (r["class"] == cls and r["split"] == "train") or id(r) in keep_ids]
    return out, dropped


def main():
    parts = {"own": own_rows(), "esc50": esc50_rows(), "aihub": aihub_rows(), "audioset": audioset_rows(),
             "cryceleb": generic_rows("cryceleb"), "fsd50k": generic_rows("fsd50k")}
    parts["rerecord"] = rerecord_rows([r for k, p in parts.items() if k != "own" for r in p])
    rows = [r for p in parts.values() for r in p]
    for k, p in parts.items():
        print(f"  {k:9s} {len(p):5d}줄")
    for cls, cap in M["train_cap"].items():
        rows, dropped = cap_train(rows, cls, cap)
        if dropped:
            print(f"학습 {cls} 상한 {cap}: 공개 데이터 {dropped}개를 뺌 (직접 녹음·재녹음·ESC-50은 모두 넣고 나머지를 묶음별로 고르게)")
    with open(DATA / "meta.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        w.writerows(rows)
    print(f"저장: data/meta.csv ({len(rows)}줄)")


if __name__ == "__main__":
    main()
