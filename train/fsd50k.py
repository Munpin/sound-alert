"""5. FSD50K 노크(개발용 270개): 꺼내기 → 올린 사람 단위 분할 → 휴대폰 모양 16 kHz 2초 창.

사용법
  python train/fsd50k.py extract   # 반디집 명령줄(bz.exe)로 분할 압축에서 Knock wav만 꺼냄 → data/raw_public/fsd50k/audio/
  python train/fsd50k.py windows   # 분할·창 → data/raw_public/fsd50k/wav16k/, windows.csv

규칙
  - 클래스: Knock 라벨이 있는 클립 → knock (모두 Door 라벨도 함께 붙어 있음)
  - 묶음 ID = 올린 사람(uploader). 같은 사람은 같은 문·같은 장비일 가능성이 커서
  - 분할: 올린 사람 단위로 학습 70 / 검증 15 / 시험 15 (FSD50K의 train/val 구분은 쓰지 않음)
  - 2초 미만 클립은 뺀다 (AI Hub와 같은 결정, 2026-11-27). 창은 가장 큰 2초, −55 dBFS 미만은 뺌
  - 라이선스는 클립마다 meta.csv에 적는다 (CC0 / BY / BY-NC / Sampling+)
"""

import collections
import csv
import json
import random
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))
from audio_prep import best_window, parse_wav, to_phone_16k, write_wav16  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "data" / "raw_public" / "fsd50k"
ZIP = D / "zip"
BZ = Path(r"C:\Program Files\Bandizip\bz.exe")
LABEL = "Knock"
RATIOS = {"train": 0.70, "val": 0.15, "test": 0.15}


def knock_clips():
    import zipfile
    gt = zipfile.ZipFile(ZIP / "FSD50K.ground_truth.zip").read("FSD50K.ground_truth/dev.csv").decode("utf-8").splitlines()
    rows = [r for r in csv.DictReader(gt) if LABEL in r["labels"].split(",")]
    meta = json.loads(zipfile.ZipFile(ZIP / "FSD50K.metadata.zip").read("FSD50K.metadata/dev_clips_info_FSD50K.json"))
    for r in rows:
        m = meta[r["fname"]]
        r["uploader"] = m["uploader"]
        lic = m["license"]
        r["license"] = ("CC0" if "zero" in lic else "CC BY-NC" if "by-nc" in lic else "CC BY" if "/by/" in lic
                        else "Sampling+" if "sampling" in lic else lic)
    return rows


def cmd_extract():
    rows = knock_clips()
    out = D / "audio"
    out.mkdir(parents=True, exist_ok=True)
    names = [f"FSD50K.dev_audio/{r['fname']}.wav" for r in rows]
    lst = D / "knock_files.txt"
    lst.write_text("\n".join(names), encoding="utf-8")
    # bz x -o:<폴더> <압축> <파일들...>  (분할 압축 .z01~.zip은 .zip을 주면 함께 읽는다)
    for k in range(0, len(names), 60):
        cmd = [str(BZ), "x", "-y", f"-o:{out}", str(ZIP / "FSD50K.dev_audio.zip")] + names[k:k + 60]
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="cp949", errors="replace")
        print(f"  bz {k + 1}~{min(k + 60, len(names))}: exit {r.returncode}")
    got = list(out.rglob("*.wav"))
    print(f"꺼낸 wav {len(got)} / {len(rows)}")


def cmd_windows():
    rows = knock_clips()
    files = {p.stem: p for p in (D / "audio").rglob("*.wav")}
    # 올린 사람 단위 분할 (클립 수가 70/15/15에 가깝도록, 큰 사람부터 욕심쟁이 배정)
    by_up = collections.defaultdict(list)
    for r in rows:
        by_up[r["uploader"]].append(r)
    rng = random.Random(0)
    ups = sorted(by_up, key=lambda u: (-len(by_up[u]), rng.random()))
    load = {s: 0 for s in RATIOS}
    total = len(rows)
    assign = {}
    for u in ups:
        s = min(RATIOS, key=lambda s: (load[s] + len(by_up[u])) / total - RATIOS[s])
        assign[u] = s
        load[s] += len(by_up[u])
    out, skip = [], collections.Counter()
    for r in rows:
        p = files.get(r["fname"])
        if p is None:
            skip["wav 없음"] += 1
            continue
        x, sr = parse_wav(p.read_bytes())
        dur = len(x) / sr
        if dur < 2.0:
            skip["2초 미만"] += 1
            continue
        y = to_phone_16k(x, sr)
        bw = best_window(y, 2.0)
        if bw is None or bw[1] < -55:
            skip["너무 조용함"] += 1
            continue
        i, rms = bw
        name = f"fsd50k_{r['fname']}.wav"
        write_wav16(D / "wav16k" / name, y[i:i + 32000])
        out.append({"file": name, "cls": "knock", "group_id": f"fsd50k:{r['uploader']}", "split": assign[r["uploader"]],
                    "license": r["license"], "note": f"FSD50K dev {r['fname']}, {dur:.1f}초 중 {i / 16000:.2f}초부터",
                    "win_start": 0.0, "orig_path": str(p.relative_to(D)).replace("\\", "/"),
                    "orig_start_sec": round(i / 16000, 3)})
    with open(D / "windows.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    c = collections.Counter(o["split"] for o in out)
    g = {s: len({o["group_id"] for o in out if o["split"] == s}) for s in RATIOS}
    lic = collections.Counter(o["license"] for o in out)
    print(f"Knock {len(rows)}개 → 창 {len(out)}개, 뺀 것 {dict(skip)}")
    print("분할: " + ", ".join(f"{s} {c[s]}개(올린 사람 {g[s]}명)" for s in RATIOS))
    print(f"라이선스: {dict(lic)}")


if __name__ == "__main__":
    cmds = {"extract": cmd_extract, "windows": cmd_windows}
    if len(sys.argv) < 2 or sys.argv[1] not in cmds:
        print(__doc__)
        sys.exit(1)
    cmds[sys.argv[1]]()
