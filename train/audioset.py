"""4. AudioSet 'Baby cry, infant cry'(/t/dd00002) 평가용 영상 → 아기 울음 시험 데이터.

사용법
  python train/audioset.py download   # 목록 찾기 → yt-dlp로 10초 구간 소리 받기 → 휴대폰 모양 16 kHz
  python train/audioset.py sheet      # 파일마다 스펙트로그램을 한 장에 모은 목록 그림 + 울음 창 후보 표

결과
  data/raw_public/audioset/babycry_eval.csv   목록과 받기 결과(성공/실패 이유)
  data/raw_public/audioset/orig/              받은 원본 소리(wav)
  data/raw_public/audioset/wav16k/            16 kHz 모노 10초 (크롬 모양 필터)
  data/raw_public/audioset/cry_windows.csv    2초 울음 창 후보(자동 제안) — 사람이 그림을 보고 고친다
  docs/figures/audioset_babycry_<번호>_1127.png  목록 그림
"""

import csv
import sys
import time
from pathlib import Path

import numpy as np

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))
from audio_prep import SR, best_window, parse_wav, to_phone_16k, write_wav16  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw_public" / "audioset"
EVAL_URL = "http://storage.googleapis.com/us_audioset/youtube_corpus/v1/csv/eval_segments.csv"
LABEL = "/t/dd00002"
LIST_CSV = OUT / "babycry_eval.csv"
WIN_CSV = OUT / "cry_windows.csv"


def fetch_list():
    import urllib.request
    OUT.mkdir(parents=True, exist_ok=True)
    src = OUT / "eval_segments.csv"
    if not src.exists():
        urllib.request.urlretrieve(EVAL_URL, src)
    rows = []
    for line in src.read_text(encoding="utf-8").splitlines():
        if line.startswith("#"):
            continue
        ytid, start, end, labels = [p.strip() for p in line.split(",", 3)]
        if LABEL in labels.strip('"').split(","):
            rows.append({"ytid": ytid, "start": float(start), "end": float(end), "labels": labels.strip('"')})
    return rows


def cmd_download():
    import imageio_ffmpeg
    import yt_dlp
    from yt_dlp.utils import download_range_func
    rows = fetch_list()
    print(f"평가 목록에서 {LABEL} 영상 {len(rows)}개")
    # yt-dlp는 파일 이름이 ffmpeg(.exe)인 것만 알아본다. imageio-ffmpeg의 실행 파일을 그 이름으로 복사해 쓴다.
    import shutil
    tool_dir = ROOT / "data" / "checks" / "tools"
    ffmpeg = tool_dir / "ffmpeg.exe"
    if not ffmpeg.exists():
        tool_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy(imageio_ffmpeg.get_ffmpeg_exe(), ffmpeg)
    ffmpeg = str(tool_dir)
    import os
    os.environ["PATH"] = ffmpeg + os.pathsep + os.environ.get("PATH", "")  # 구간 다운로드는 PATH에서만 ffmpeg를 찾는다
    (OUT / "orig").mkdir(parents=True, exist_ok=True)
    for k, r in enumerate(rows, 1):
        name = f"{r['ytid']}_{int(r['start'])}"
        wav = OUT / "orig" / f"{name}.wav"
        r["file"] = f"audioset_{name}.wav"
        if not wav.exists():
            opts = {
                "format": "bestaudio/best", "quiet": True, "no_warnings": True, "noprogress": True,
                "outtmpl": str(OUT / "orig" / f"{name}.%(ext)s"), "ffmpeg_location": ffmpeg,
                "download_ranges": download_range_func(None, [(r["start"], r["end"])]), "force_keyframes_at_cuts": True,
                "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "wav"}],
                "js_runtimes": {"node": {}},
            }
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.download([f"https://www.youtube.com/watch?v={r['ytid']}"])
            except Exception as e:  # noqa: BLE001
                msg = str(e).replace("\n", " ")
                r["status"] = "실패"
                r["reason"] = msg.split("ERROR: ")[-1][:160]
                print(f"  [{k:2d}] {r['ytid']} 실패: {r['reason']}")
                time.sleep(1.0)
                continue
            time.sleep(1.0)
        if not wav.exists():
            r["status"], r["reason"] = "실패", "wav 파일이 만들어지지 않음"
            continue
        x, sr = parse_wav(wav.read_bytes())
        y = to_phone_16k(x, sr)[: 10 * SR]
        write_wav16(OUT / "wav16k" / r["file"], y)
        r["status"], r["reason"] = "성공", f"원본 {sr} Hz {x.shape[1]}ch {len(x) / sr:.2f}초 → 16k {len(y) / SR:.2f}초"
        print(f"  [{k:2d}] {r['ytid']} 성공 ({r['reason']})")
    with open(LIST_CSV, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["ytid", "start", "end", "labels", "file", "status", "reason"])
        w.writeheader()
        w.writerows(rows)
    ok = sum(r.get("status") == "성공" for r in rows)
    print(f"\n성공 {ok} / {len(rows)}")
    reasons = {}
    for r in rows:
        if r.get("status") != "성공":
            key = r.get("reason", "")[:60]
            reasons[key] = reasons.get(key, 0) + 1
    for k, v in sorted(reasons.items(), key=lambda kv: -kv[1]):
        print(f"  실패 {v}개: {k}")


def cmd_sheet():
    from check_wav import load_pyplot, spectrogram_db
    rows = [r for r in csv.DictReader(open(LIST_CSV, encoding="utf-8")) if r["status"] == "성공"]
    plt = load_pyplot()
    per = 36
    wins = []
    for page in range(0, len(rows), per):
        chunk = rows[page:page + per]
        fig, axes = plt.subplots(12, 3, figsize=(15, 31))
        for ax in axes.flat:
            ax.axis("off")
        for j, r in enumerate(chunk):
            idx = page + j + 1
            x, _ = parse_wav((OUT / "wav16k" / r["file"]).read_bytes())
            y = x[:, 0]
            db, f, t = spectrogram_db(y, SR)
            ax = axes.flat[j]
            ax.axis("on")
            vmax = np.percentile(db, 99.5)
            ax.pcolormesh(t, f / 1000, db, shading="auto", cmap="magma", vmin=vmax - 70, vmax=vmax)
            bw = best_window(y, 2.0)
            s = bw[0] / SR if bw else 0.0
            ax.add_patch(plt.Rectangle((s, 0.1), 2.0, 7.8, fill=False, ec="#00e676", lw=1.6))
            ax.set_title(f"{idx}. {r['ytid']}  (자동 후보 {s:.1f}~{s + 2:.1f}초)", fontsize=9)
            ax.set_xlim(0, 10)
            ax.set_xticks(range(0, 11, 2))
            ax.tick_params(labelsize=7)
            if j % 3 == 0:
                ax.set_ylabel("kHz", fontsize=8)
            wins.append({"no": idx, "file": r["file"], "ytid": r["ytid"], "auto_start_sec": round(s, 1),
                         "use_start_sec": "", "note": ""})
        fig.suptitle("AudioSet 'Baby cry, infant cry' 평가용 — 가로 시간(초), 세로 주파수(kHz). 초록 상자 = 자동으로 고른 2초 창(가장 큰 소리)", fontsize=12)
        fig.tight_layout(rect=(0, 0, 1, 0.985))
        out = ROOT / "docs" / "figures" / f"audioset_babycry_{page // per + 1}_1127.png"
        fig.savefig(out, dpi=80)
        plt.close(fig)
        print(f"그림: {out.relative_to(ROOT)}")
    with open(WIN_CSV, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["no", "file", "ytid", "auto_start_sec", "use_start_sec", "note"])
        w.writeheader()
        w.writerows(wins)
    print(f"후보 표: {WIN_CSV.relative_to(ROOT)} ({len(wins)}개)")


if __name__ == "__main__":
    cmds = {"download": cmd_download, "sheet": cmd_sheet}
    if len(sys.argv) < 2 or sys.argv[1] not in cmds:
        print(__doc__)
        sys.exit(1)
    cmds[sys.argv[1]]()
