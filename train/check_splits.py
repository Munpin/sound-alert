"""8. 분할 검사와 데이터 현황 (data/meta.csv 기준).

  1) 모든 묶음(group_id)이 한 분할에만 있는가
  2) 클래스 × 분할 × 출처 개수 표
  3) 시험 A(휴대폰 경로: 직접 녹음 + 재녹음)가 6종을 모두 담는가
  4) 부족한 칸을 빨간색으로 표시한 그림 docs/figures/data_counts_<MMDD>.png

사용법: python train/check_splits.py [--date 1127]
"""

import argparse
import collections
import csv
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))
from check_wav import load_pyplot  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CFG = json.loads((ROOT / "train" / "config.json").read_text(encoding="utf-8"))
CLASSES = CFG["classes"]
SPLITS = ["train", "val", "test"]
T = CFG["meta"]["targets"]


def src_group(s):
    return "rerecord" if s.startswith("rerecord:") else s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="1127")
    args = ap.parse_args()
    rows = list(csv.DictReader(open(ROOT / "data" / "meta.csv", encoding="utf-8")))
    ok = True
    print(f"meta.csv {len(rows)}줄")

    # 1) 묶음 검사
    gs = collections.defaultdict(set)
    for r in rows:
        if r["split"] in SPLITS:
            gs[r["group_id"]].add(r["split"])
    multi = {g: s for g, s in gs.items() if len(s) > 1}
    print(f"\n== 1) 묶음 검사: 묶음 {len(gs)}개, 여러 분할에 걸친 묶음 {len(multi)}개 ==")
    for g, s in list(multi.items())[:20]:
        print(f"  [실패] {g}: {sorted(s)}")
    ok &= not multi
    un = collections.Counter(r["class"] for r in rows if r["split"] not in SPLITS)
    if un:
        print(f"  [알림] 분할이 정해지지 않은 줄(unassigned): {dict(un)}")

    # 2) 개수 표
    srcs = ["own", "rerecord", "esc50", "aihub", "audioset", "cryceleb", "fsd50k"]
    cnt = collections.Counter((r["class"], r["split"], src_group(r["source"])) for r in rows)
    print("\n== 2) 클래스 × 분할 × 출처 ==")
    print(f"{'':10s}{'분할':6s}" + "".join(f"{s:>10s}" for s in srcs) + f"{'합계':>8s}")
    totals = {}
    for c in CLASSES:
        for sp in SPLITS + ["unassigned"]:
            vals = [cnt[(c, sp, s)] for s in srcs]
            if sp == "unassigned" and not sum(vals):
                continue
            totals[(c, sp)] = sum(vals)
            print(f"{c:10s}{sp:6s}" + "".join(f"{v:10d}" for v in vals) + f"{sum(vals):8d}")

    # 2-1) 나눠서 점수를 낼 칸: 경적은 소분류, 아기 울음은 원래 출처
    print("\n== 2-1) 경적 시험: 소분류별 (subclass) ==")
    for k, v in sorted(collections.Counter(r["subclass"] for r in rows if r["class"] == "horn" and r["split"] == "test").items()):
        print(f"  {k:24s} {v:4d}")
    print("== 2-1) 아기 울음: 원래 출처별 (orig_source) ==")
    for sp in SPLITS:
        c = collections.Counter(r["orig_source"] for r in rows if r["class"] == "baby_cry" and r["split"] == sp)
        print(f"  {sp:5s} " + ", ".join(f"{k} {v}" for k, v in sorted(c.items())))

    # 3) 시험 A
    a = collections.Counter(r["class"] for r in rows if r["split"] == "test" and src_group(r["source"]) in ("own", "rerecord"))
    missing = [c for c in CLASSES if a[c] == 0]
    print(f"\n== 3) 시험 A(직접 녹음 + 재녹음, test): {dict(a)} ==")
    print(f"  [{'통과' if not missing else '부족'}] 6종 모두 있음" + ("" if not missing else f" — 없는 클래스: {missing}"))
    ok &= not missing

    # 부족한 칸
    short = []
    for c in CLASSES:
        need_t = T["test_min_baby_cry"] if c == "baby_cry" else T["test_min"]
        if totals.get((c, "test"), 0) < need_t:
            short.append((c, "test", totals.get((c, "test"), 0), need_t))
        if totals.get((c, "val"), 0) < T["val_min"]:
            short.append((c, "val", totals.get((c, "val"), 0), T["val_min"]))
    print("\n== 부족한 칸 (시험 30개 이상, 아기 울음 50개 이상, 검증 20개 이상) ==")
    for c, sp, n, need in short:
        print(f"  {c:9s} {sp:5s} {n:4d} < {need}")
    if not short:
        print("  없음")

    # 4) 그림
    plt = load_pyplot()
    cols = [(sp, s) for sp in SPLITS for s in srcs] + [(sp, "합계") for sp in SPLITS] + [("test", "시험 A")]
    fig, ax = plt.subplots(figsize=(19, 4.6))
    ax.axis("off")
    cell = []
    colors = []
    for c in CLASSES:
        line, cl = [], []
        for sp, s in cols:
            if s == "합계":
                v = totals.get((c, sp), 0)
                need = (T["test_min_baby_cry"] if c == "baby_cry" else T["test_min"]) if sp == "test" else (T["val_min"] if sp == "val" else 0)
                cl.append("#f8c8c8" if v < need or v == 0 else "#d7ecd9")
            elif s == "시험 A":
                v = a[c]
                cl.append("#f8c8c8" if v == 0 else "#d7ecd9")
            else:
                v = cnt[(c, sp, s)]
                cl.append("#ffffff")
            line.append(str(v) if v else "·")
        cell.append(line)
        colors.append(cl)
    labels = [f"{sp}\n{s}" for sp, s in cols]
    tb = ax.table(cellText=cell, cellColours=colors, rowLabels=CLASSES, colLabels=labels, loc="center", cellLoc="center")
    tb.auto_set_font_size(False)
    tb.set_fontsize(8)
    tb.scale(1, 1.7)
    ax.set_title(f"2초 창 개수 (클래스 × 분할 × 출처, data/meta.csv) — 빨강: 0개, 시험 30개(아기 울음 50) 또는 검증 20개 미만, 시험 A에 없음", fontsize=11)
    out = ROOT / "docs" / "figures" / f"data_counts_{args.date}.png"
    fig.tight_layout()
    fig.savefig(out, dpi=120)
    print(f"\n그림: {out.relative_to(ROOT)}")
    print("\n결과:", "분할 검사 통과" if not multi else "분할 검사 실패", "/", "시험 A 6종 있음" if not missing else "시험 A 부족")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
