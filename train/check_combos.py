"""직접 녹음 회차 조합 검사 (data/sessions.csv).

설계서 4절: 시험 회차는 학습에 없던 위치·배경 조합으로 만든다. 검증도 학습과 겹치지 않게 짠다(11/28 계획).
  - 직접 녹음 회차만 본다(source=own, 클래스 doorbell·knock). 스피커 재녹음 회차는 원본의 분할을 따르므로 뺀다.
  - 조합 = (장소, 배경). 클래스는 따지지 않는다(배경 단서는 클래스와 상관없이 외울 수 있어서).
  - 같은 자리로 보는 장소: kitchen = entrance (원룸에서 부엌이 현관 앞과 거의 같은 자리, 11/28 사용자)

사용법: python train/check_combos.py
"""

import collections
import csv
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[1]
SAME_PLACE = {"kitchen": "entrance"}


def main():
    rows = [r for r in csv.DictReader(open(ROOT / "data" / "sessions.csv", encoding="utf-8"))
            if r["source"] == "own" and r["class"] in ("doorbell", "knock") and r["split"]]
    combos = collections.defaultdict(list)
    for r in rows:
        key = (SAME_PLACE.get(r["place"], r["place"]), r["background"])
        combos[r["split"]].append((key, r["group_id"], r["class"]))
    train = {k for k, _, _ in combos["train"]}
    print("# 직접 녹음 회차 조합 검사 (장소, 배경). kitchen은 entrance와 같은 자리로 봄")
    for sp in ("train", "val", "test"):
        print(f"\n[{sp}] {len(combos[sp])}회차")
        for k, g, c in combos[sp]:
            print(f"  {g:16s} {c:9s} {k[0]:9s} + {k[1]}")
    bad = []
    for sp in ("val", "test"):
        for k, g, c in combos[sp]:
            if k in train:
                bad.append((sp, g, k))
    val = {k for k, _, _ in combos["val"]}
    test_val = [(g, k) for k, g, _ in combos["test"] if k in val]
    print("\n== 결과 ==")
    for sp, g, k in bad:
        print(f"  [겹침] {sp} {g}: {k} 가 학습에 있음")
    for g, k in test_val:
        print(f"  [알림] 시험 {g}: {k} 가 검증에도 있음")
    print("  검증·시험이 학습과 겹치는 조합: " + ("없음 (통과)" if not bad else f"{len(bad)}개 (실패)"))
    n = collections.Counter((r["class"], r["split"]) for r in rows)
    print("\n회차 수: " + ", ".join(f"{c} {sp} {n[(c, sp)]}" for c in ("doorbell", "knock") for sp in ("train", "val", "test")))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
