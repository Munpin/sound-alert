"""6. 스피커 재녹음용 재생 파일 만들기.

meta.csv에서 고른 공개 데이터 2초 창들을 원본 음질(48 kHz)로 이어 붙인다.
  맨 앞: 시작 신호음 1 kHz 0.5초 → 2초 무음 → [창 2초 + 무음 2초] × n → 끝 신호음 1 kHz 0.5초
  (앞뒤 신호음 두 개로 재생기와 휴대폰의 시계 차이를 맞춘다)
  창마다 음량을 맞춘다(RMS −23 dBFS, 최고점 −1 dBFS 이하). 앞뒤 10 ms는 부드럽게 켜고 끈다.
결과
  data/raw/rerecord/playlists/<이름>.wav  (48 kHz 모노 16비트, 휴대폰 옆 스피커로 재생)
  data/raw/rerecord/playlists/<이름>.csv  (창마다 재생 파일 안 시작 시각과 원본 정보)

재녹음 파일은 원본의 분할을 그대로 따른다(설계서 4절). 그래서 같은 분할 안에서만 고른다.

사용법
  python train/make_playlist.py --split test --cls siren --n 30
  python train/make_playlist.py --split val --cls baby_cry --n 25 --sources audioset,cryceleb,esc50
"""

import argparse
import collections
import csv
import io
import json
import random
import sys
import wave
import zipfile
from pathlib import Path

import numpy as np
import soxr

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))
from audio_prep import parse_wav  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CFG = json.loads((ROOT / "train" / "config.json").read_text(encoding="utf-8"))
OUT = DATA / "raw" / "rerecord" / "playlists"
PLAY_SR = 48000
TONE_HZ, TONE_SEC, GAP_SEC, WIN = 1000.0, 0.5, 2.0, 2.0
TARGET_RMS_DB, PEAK_DB = -23.0, -1.0
PUBLIC = ("esc50", "aihub", "audioset", "cryceleb", "fsd50k")


def _lookup(path, key):
    return {r[key]: r for r in csv.DictReader(open(path, encoding="utf-8-sig"))} if Path(path).exists() else {}


def load_original(r, cache={}):
    """meta.csv 한 줄 → (원본 음질 2초 mono float, sr). 공개 데이터만."""
    src = r["source"]
    name = Path(r["file"]).name
    if src == "aihub":
        w = cache.setdefault("aihub", _lookup(DATA / "raw_public/aihub/windows.csv", "file"))[name]
        zroot = Path(CFG["paths"]["aihub_zip_root"]).expanduser()
        from aihub import real_name, INDEX_CSV
        idx = cache.setdefault("aihub_idx", _lookup(INDEX_CSV, "member"))[w["member"]]
        zf = cache.setdefault(("zip", idx["zip"]), zipfile.ZipFile(zroot / idx["zip"]))
        names = cache.setdefault(("names", idx["zip"]), {real_name(i): i for i in zf.infolist()})
        x, sr = parse_wav(zf.read(names[w["member"]]))
        st = float(w["win_start_sec"])
    elif src == "esc50":
        w = cache.setdefault("esc50", _lookup(DATA / "raw_public/esc50/windows.csv", "file"))[name]
        x, sr = parse_wav((DATA / "raw_public/esc50/ESC-50-master/audio" / w["orig"]).read_bytes())
        st = float(w["win_start_sec"])
    elif src == "audioset":
        x, sr = parse_wav((DATA / "raw_public/audioset/orig" / name.replace("audioset_", "")).read_bytes())
        st = float(r["win_start"])
    elif src in ("cryceleb", "fsd50k"):
        w = cache.setdefault(src, _lookup(DATA / f"raw_public/{src}/windows.csv", "file"))[name]
        x, sr = parse_wav((DATA / f"raw_public/{src}" / w["orig_path"]).read_bytes())
        st = float(w["orig_start_sec"])
    else:
        raise ValueError(f"재녹음 원본으로 쓸 수 없는 출처: {src}")
    x = x.mean(axis=1)
    i = int(round(st * sr))
    seg = x[i:i + int(WIN * sr)]
    if len(seg) < int(WIN * sr):
        seg = np.pad(seg, (0, int(WIN * sr) - len(seg)))
    return seg, sr


def level(seg):
    rms = np.sqrt(np.mean(seg ** 2) + 1e-12)
    g = 10 ** (TARGET_RMS_DB / 20) / rms
    peak = np.abs(seg).max() * g
    if peak > 10 ** (PEAK_DB / 20):
        g *= 10 ** (PEAK_DB / 20) / peak
    y = seg * g
    f = int(0.01 * PLAY_SR)
    ramp = np.linspace(0, 1, f)
    y[:f] *= ramp
    y[-f:] *= ramp[::-1]
    return y, 20 * np.log10(g)


def pick(rows, n, seed):
    """묶음을 돌아가며 n개 (출처도 돌아가며)"""
    rng = random.Random(seed)
    by = collections.defaultdict(lambda: collections.defaultdict(list))
    for r in rows:
        by[r["source"]][r["group_id"]].append(r)
    queues = {}
    for s, gs in by.items():
        gl = list(gs.values())
        for g in gl:
            rng.shuffle(g)
        rng.shuffle(gl)
        queues[s] = gl
    out = []
    while len(out) < n and any(queues.values()):
        for s in sorted(queues):
            gl = queues[s]
            if gl and len(out) < n:
                g = gl.pop(0)
                out.append(g.pop(0))
                if g:
                    gl.append(g)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", required=True, choices=["val", "test"])
    ap.add_argument("--cls", required=True)
    ap.add_argument("--n", type=int, required=True)
    ap.add_argument("--sources", default="", help="쉼표로 출처 제한 (기본: 공개 데이터 전부)")
    ap.add_argument("--name", default="")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    srcs = tuple(args.sources.split(",")) if args.sources else PUBLIC
    rows = [r for r in csv.DictReader(open(DATA / "meta.csv", encoding="utf-8"))
            if r["split"] == args.split and r["class"] == args.cls and r["source"] in srcs]
    chosen = pick(rows, args.n, args.seed)
    if len(chosen) < args.n:
        print(f"[경고] 후보가 {len(rows)}개라 {len(chosen)}개만 고름")
    name = args.name or f"{args.cls}_{args.split}"
    tone_t = np.arange(int(TONE_SEC * PLAY_SR)) / PLAY_SR
    tone = 0.5 * np.sin(2 * np.pi * TONE_HZ * tone_t)
    f = int(0.01 * PLAY_SR)
    tone[:f] *= np.linspace(0, 1, f)
    tone[-f:] *= np.linspace(1, 0, f)
    gap = np.zeros(int(GAP_SEC * PLAY_SR))
    parts, meta, t = [tone, gap], [], TONE_SEC + GAP_SEC
    for k, r in enumerate(chosen, 1):
        seg, sr = load_original(r)
        y = soxr.resample(seg, sr, PLAY_SR, quality="VHQ") if sr != PLAY_SR else seg
        y = y[: int(WIN * PLAY_SR)]
        y, gain_db = level(y)
        parts += [y, gap]
        meta.append({"idx": k, "start_sec": round(t, 4), "end_sec": round(t + WIN, 4), "meta_file": r["file"],
                     "meta_win_start": r["win_start"], "cls": r["class"], "group_id": r["group_id"], "split": r["split"],
                     "source": r["source"], "license": r["license"], "orig_sr": sr, "gain_db": round(gain_db, 2)})
        t += WIN + GAP_SEC
    end_tone_sec = t
    parts.append(tone)
    audio = np.concatenate(parts)
    OUT.mkdir(parents=True, exist_ok=True)
    with wave.open(str(OUT / f"{name}.wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(PLAY_SR)
        w.writeframes(np.clip(np.round(audio * 32767), -32768, 32767).astype("<i2").tobytes())
    for m in meta:
        m["end_tone_sec"] = round(end_tone_sec, 4)
    with open(OUT / f"{name}.csv", "w", encoding="utf-8", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(meta[0]))
        wr.writeheader()
        wr.writerows(meta)
    c = collections.Counter(m["source"] for m in meta)
    print(f"재생 파일: data/raw/rerecord/playlists/{name}.wav ({len(audio) / PLAY_SR:.1f}초, 창 {len(meta)}개, 출처 {dict(c)}, "
          f"묶음 {len({m['group_id'] for m in meta})}개)")


if __name__ == "__main__":
    main()
