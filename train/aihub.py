"""AI Hub 도시 소리 데이터: 원본 압축(다운로드 폴더)에서 직접 읽는다. 원본은 복사·수정하지 않는다.

사용법
  python train/aihub.py list      # 2-1: 소분류 목록·개수, 라벨 칸 이름, 날짜·장소 묶음 수

원본 위치는 train/config.json의 paths.aihub_zip_root.
"""

import collections
import json
import sys
import zipfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
CFG = json.loads((ROOT / "train" / "config.json").read_text(encoding="utf-8"))
ZIP_ROOT = Path(CFG["paths"]["aihub_zip_root"]).expanduser()

# (분할, 종류 번호, 원천 zip, 라벨 zip)
ZIPS = [
    ("Training", 1, "1.Training/원천데이터/TS_1.교통소음.zip", "1.Training/라벨링데이터/TL_1.교통소음.zip"),
    ("Training", 2, "1.Training/원천데이터/TS_2.생활소음.zip", "1.Training/라벨링데이터/TL_2.생활소음.zip"),
    ("Training", 3, "1.Training/원천데이터/TS_3.사업장소음.zip", "1.Training/라벨링데이터/TL_3.사업장소음.zip"),
    ("Validation", 1, "2.Validation/원천데이터/VS_1.교통소음.zip", "2.Validation/라벨링데이터/VL_1.교통소음.zip"),
    ("Validation", 2, "2.Validation/원천데이터/VS_2.생활소음.zip", "2.Validation/라벨링데이터/VL_2.생활소음.zip"),
    ("Validation", 3, "2.Validation/원천데이터/VS_3.사업장소음.zip", "2.Validation/라벨링데이터/VL_3.사업장소음.zip"),
]
KIND = {1: "교통소음", 2: "생활소음", 3: "사업장소음"}


def real_name(info):
    """zip 안 한글 이름 복원 (AI Hub zip은 cp949로 저장돼 있다)"""
    if info.flag_bits & 0x800:
        return info.filename
    try:
        return info.filename.encode("cp437").decode("cp949")
    except UnicodeError:
        return info.filename


def read_json(zf, info):
    raw = zf.read(info)
    for enc in ("utf-8-sig", "cp949"):
        try:
            return json.loads(raw.decode(enc))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
    raise ValueError(f"json 읽기 실패: {real_name(info)}")


def key_tree(d, prefix=""):
    """json 칸 이름을 점 경로로 (예: environment.district)"""
    out = []
    for k, v in d.items():
        p = f"{prefix}{k}"
        if isinstance(v, dict):
            out += key_tree(v, p + ".")
        elif isinstance(v, list) and v and isinstance(v[0], dict):
            out += key_tree(v[0], p + "[].")
        else:
            out.append((p, v))
    return out


def cmd_list():
    print(f"원본 위치: {ZIP_ROOT}")
    wav_count = collections.Counter()      # (분할, 소분류) → wav 수
    wav_bytes = collections.Counter()
    json_info = {}                         # (분할, 종류) → [(소분류, json dict)]
    for split, kind, wz, lz in ZIPS:
        zw = zipfile.ZipFile(ZIP_ROOT / wz)
        for i in zw.infolist():
            if i.is_dir():
                continue
            n = real_name(i)
            if n.lower().endswith(".wav"):
                cat = n.rsplit("/", 1)[0]
                wav_count[(split, cat)] += 1
                wav_bytes[(split, cat)] += i.file_size
        if kind == 3:
            continue  # 사업장소음은 소분류만 본다
        zl = zipfile.ZipFile(ZIP_ROOT / lz)
        items = []
        for i in zl.infolist():
            if i.is_dir() or not real_name(i).lower().endswith(".json"):
                continue
            items.append((real_name(i).rsplit("/", 1)[0], read_json(zl, i)))
        json_info[(split, kind)] = items

    # ---- 1) 소분류 목록과 개수
    cats = sorted({c for _, c in wav_count}, key=lambda c: [int(p.split(".")[0]) if p.split(".")[0].isdigit() else p for p in c.split("/")])
    print("\n== 1) 소분류별 wav 개수 (원천 zip) ==")
    print(f"{'소분류':28s} {'Training':>9s} {'Validation':>11s} {'합계':>7s} {'용량(GB)':>9s}")
    for c in cats:
        t, v = wav_count[("Training", c)], wav_count[("Validation", c)]
        gb = (wav_bytes[("Training", c)] + wav_bytes[("Validation", c)]) / 1e9
        print(f"{c:28s} {t:9d} {v:11d} {t + v:7d} {gb:9.2f}")

    # ---- 2) 라벨 json 칸 이름 (교통소음 첫 파일)
    first = json_info[("Training", 1)][0][1]
    print("\n== 2) 라벨 json 칸 이름과 예시 값 (TL_1 첫 파일) ==")
    for p, v in key_tree(first):
        print(f"  {p:40s} {str(v)[:50]}")

    # ---- 3) 날짜·장소 묶음 수
    def gkeys(d):
        env, info = d.get("environment", {}), d.get("info", {})
        return {
            "date": info.get("dateCreated"),
            "date+district": (info.get("dateCreated"), env.get("urban"), env.get("district")),
            "date+district+place": (info.get("dateCreated"), env.get("urban"), env.get("district"), env.get("place")),
        }

    print("\n== 3) 소분류별 json 수와 묶음 수 (Training+Validation 합침) ==")
    print("   묶음 후보: date=info.dateCreated / district=environment.urban+district / place=environment.place")
    print("   겹침 = 같은 묶음이 AI Hub Training과 Validation 양쪽에 있는 수")
    rows = collections.defaultdict(lambda: {"n": 0, "ann": 0, "dur": 0.0, "g": collections.defaultdict(lambda: collections.defaultdict(set))})
    for (split, kind), items in json_info.items():
        for cat, d in items:
            r = rows[cat]
            r["n"] += 1
            r["ann"] += len(d.get("annotations", []))
            r["dur"] += float(d.get("audio", {}).get("duration") or 0)
            for k, g in gkeys(d).items():
                r["g"][k][g].add(split)
    print(f"{'소분류':28s} {'json':>6s} {'소리구간':>8s} {'총길이(시간)':>11s} | {'date':>10s} {'date+district':>15s} {'date+district+place':>21s}")
    for c in sorted(rows, key=lambda c: [int(p.split('.')[0]) if p.split('.')[0].isdigit() else p for p in c.split('/')]):
        r = rows[c]
        cells = []
        for k in ["date", "date+district", "date+district+place"]:
            g = r["g"][k]
            both = sum(1 for s in g.values() if len(s) > 1)
            cells.append(f"{len(g)}(겹침 {both})")
        print(f"{c:28s} {r['n']:6d} {r['ann']:8d} {r['dur'] / 3600:11.1f} | {cells[0]:>10s} {cells[1]:>15s} {cells[2]:>21s}")

    # ---- 4) 장소·환경 칸의 값 종류 (교통소음 + 생활소음)
    print("\n== 4) 환경 칸 값 종류 (교통·생활소음 json 전체) ==")
    vals = collections.defaultdict(collections.Counter)
    for items in json_info.values():
        for _, d in items:
            env = d.get("environment", {})
            for k in ["urban", "place", "areaUse", "dayNight", "acqDevice", "acqMethod", "distance", "obstacle"]:
                vals[k][str(env.get(k))] += 1
            vals["sampleRate"][str(d.get("audio", {}).get("sampleRate"))] += 1
            vals["recodingType"][str(d.get("audio", {}).get("recodingType"))] += 1
            vals["license"][str(d.get("license", {}).get("name"))] += 1
    for k, c in vals.items():
        top = ", ".join(f"{v}({n})" for v, n in c.most_common(12))
        print(f"  {k:14s} {len(c):3d}종: {top}")


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] != "list":
        print(__doc__)
        sys.exit(1)
    cmd_list()
