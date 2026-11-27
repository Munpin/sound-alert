"""1. ESC-50: 클래스 대응, 원본 클립 묶음, fold 분할, 휴대폰 모양 16 kHz 2초 창.

사용법
  python train/esc50.py      → data/raw_public/esc50/wav16k/, data/raw_public/esc50/windows.csv

규칙 (docs/step2_data.md 1절)
  - door_wood_knock→knock, crying_baby→baby_cry, siren→siren, car_horn→horn, 나머지 45종→other
  - 묶음 ID = 원본 클립 번호(파일 이름 두 번째 칸, src_file)
  - fold 1~3 학습, 4 검증, 5 시험. 한 묶음이 여러 분할에 걸치면 파일이 더 많은 분할로 모은다(같으면 검증)
"""

import collections
import csv
import json
import sys
from multiprocessing import Pool
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))
from audio_prep import best_window, parse_wav, to_phone_16k, write_wav16  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CFG = json.loads((ROOT / "train" / "config.json").read_text(encoding="utf-8"))
ESC = ROOT / CFG["paths"]["esc50_root"]
OUT = ROOT / "data" / "raw_public" / "esc50"
CLASS_MAP = {"door_wood_knock": "knock", "crying_baby": "baby_cry", "siren": "siren", "car_horn": "horn"}
FOLD_SPLIT = {"1": "train", "2": "train", "3": "train", "4": "val", "5": "test"}
ORDER = {"train": 0, "val": 1, "test": 2}
MIN_DBFS = -55.0
COLS = ["file", "orig", "category", "cls", "group_id", "fold", "split", "win_start_sec", "rms_dbfs"]


def work(r):
    x, sr = parse_wav((ESC / "audio" / r["filename"]).read_bytes())
    y = to_phone_16k(x, sr)
    i, rms = best_window(y, 2.0)
    if rms < MIN_DBFS:
        return r, None, rms
    name = "esc50_" + r["filename"]
    write_wav16(OUT / "wav16k" / name, y[i:i + 32000])
    return r, {"file": name, "win_start_sec": round(i / 16000, 3), "rms_dbfs": round(rms, 2)}, rms


def main():
    rows = list(csv.DictReader(open(ESC / "meta" / "esc50.csv", encoding="utf-8")))
    for r in rows:
        assert r["filename"].split("-")[1] == r["src_file"]
        r["cls"] = CLASS_MAP.get(r["category"], "other")
        r["group_id"] = "esc50:" + r["src_file"]
        r["split"] = FOLD_SPLIT[r["fold"]]
    # 묶음이 여러 분할에 걸치면 한쪽으로
    by_g = collections.defaultdict(list)
    for r in rows:
        by_g[r["group_id"]].append(r)
    moved = []
    for g, items in by_g.items():
        c = collections.Counter(r["split"] for r in items)
        if len(c) > 1:
            target = sorted(c, key=lambda s: (-c[s], s != "val", ORDER[s]))[0]
            for r in items:
                if r["split"] != target:
                    moved.append((g, r["filename"], r["category"], r["split"], target))
                    r["split"] = target
    print(f"ESC-50 {len(rows)}개, 묶음 {len(by_g)}개")
    print(f"여러 분할에 걸친 묶음 {len({m[0] for m in moved})}개 → 옮긴 파일 {len(moved)}개")
    for m in moved:
        print(f"  {m[0]} {m[1]} ({m[2]}) {m[3]} → {m[4]}")
    out, quiet = [], []
    with Pool(6) as pool:
        for r, res, rms in pool.imap_unordered(work, rows, chunksize=16):
            if res is None:
                quiet.append((r["filename"], r["category"], round(rms, 1)))
                continue
            out.append({"orig": r["filename"], "category": r["category"], "cls": r["cls"], "group_id": r["group_id"],
                        "fold": r["fold"], "split": r["split"], **res})
    out.sort(key=lambda d: d["file"])
    with open(OUT / "windows.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        w.writerows(out)
    print(f"저장: {len(out)}개 → data/raw_public/esc50/wav16k/, windows.csv")
    print(f"너무 조용해서 뺀 창(< {MIN_DBFS} dBFS): {len(quiet)}개 {quiet[:5]}")
    print("\n== 클래스 × 분할 ==")
    for c in ["knock", "baby_cry", "siren", "horn", "other"]:
        k = collections.Counter(d["split"] for d in out if d["cls"] == c)
        print(f"  {c:9s} train {k['train']:4d}  val {k['val']:4d}  test {k['test']:4d}")
    gs = collections.defaultdict(set)
    for d in out:
        gs[d["group_id"]].add(d["split"])
    print(f"여러 분할에 걸친 묶음(옮긴 뒤): {sum(1 for v in gs.values() if len(v) > 1)}개")


if __name__ == "__main__":
    main()
