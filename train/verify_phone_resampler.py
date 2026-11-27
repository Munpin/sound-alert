"""휴대폰 크롬 16 kHz 변환 모양 확인 (model-test 페이지 4번 결과).

휴대폰에서 model-test 페이지의 "4. 크롬 16 kHz 변환 모양"을 누르고 저장한 json을 읽어,
PC 크롬 측정(data/checks/chrome_resampler/chrome_out_48000.f32)과 같은 계산으로 비교한다.
공개 데이터에 씌우는 크롬 모양 필터(train/chrome_response.json)는 PC 측정에서 만들었으므로,
휴대폰 모양이 PC와 같으면 그대로 쓰고, 다르면 휴대폰 측정으로 필터를 다시 만들어야 한다.

사용법
  python train/verify_phone_resampler.py data/raw/model_test_wasm_XXXX.json [--date 1128]
"""

import argparse
import base64
import json
import sys
from pathlib import Path

import numpy as np

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))
from check_wav import load_pyplot  # noqa: E402
from compare_resample import crossing, psd, response_db  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PC = ROOT / "data" / "checks" / "chrome_resampler" / "chrome_out_48000.f32"
BANDS = [(500, 6000), (6000, 7500), (7500, 7800), (7800, 8000)]


def curve(x):
    f, p = psd(x.astype(np.float64))
    return f, response_db(f, p)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("json", type=Path)
    ap.add_argument("--date", default="1128")
    ap.add_argument("--label", default="휴대폰")
    ap.add_argument("--fig", default="phone_resampler", help="그림 이름 앞부분 (docs/figures/<fig>_<date>.png)")
    args = ap.parse_args()
    j = json.loads(args.json.read_text(encoding="utf-8"))
    rs = j["resampler"]
    if "error" in rs:
        raise SystemExit(f"[실패] 페이지에서 측정 실패: {rs['error']}")
    x = np.frombuffer(base64.b64decode(rs["samples_b64"]), dtype="<f4")
    ua = j.get("device", {}).get("userAgent", "")
    print(f"# 크롬 16 kHz 변환 모양: {args.label} vs PC (입력 {args.json.name})")
    print(f"기기: {j.get('device', {}).get('model', '')} {ua}")
    print(f"컨텍스트 {rs['ctx48Rate']} Hz → {rs['ctx16Rate']} Hz, 받은 길이 {len(x) / 16000:.2f}초")
    f, r_ph = curve(x)
    f2, r_pc = curve(np.fromfile(PC, dtype="<f4"))
    assert np.allclose(f, f2)
    for name, r in [(args.label, r_ph), ("PC 크롬", r_pc)]:
        pts = "  ".join(f"{k / 1000:.1f}k {np.interp(k, f, r):6.1f}" for k in [6000, 6500, 7000, 7500, 7800])
        print(f"{name:8s} -1dB {crossing(f, r, -1):6.0f} Hz  -3dB {crossing(f, r, -3):6.0f} Hz  -6dB {crossing(f, r, -6):6.0f} Hz  {pts}")
    print(f"\n== {args.label} − PC (dB) ==")
    worst = 0.0
    for a, b in BANDS:
        m = (f >= a) & (f < b)
        d = r_ph[m] - r_pc[m]
        print(f"  {a / 1000:.1f}~{b / 1000:.1f} kHz: 평균 차이 {d.mean():6.2f}, 최대 |차이| {np.abs(d).max():6.2f}")
        if b <= 7800:
            worst = max(worst, abs(d.mean()))
    print(f"\n0.5~7.8 kHz 구간별 평균 차이 중 가장 큰 값: {worst:.2f} dB "
          f"(같은 PC에서 여러 번 재도 생기는 흔들림은 docs/logs/resampler_page_pc_1127.txt 참고)")

    plt = load_pyplot()
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(f / 1000, r_pc, label="PC 크롬 158 (공개 데이터 필터의 기준)", lw=1)
    ax.plot(f / 1000, r_ph, label=args.label, lw=1)
    ax.set_xlim(0, 8)
    ax.set_ylim(-40, 5)
    ax.set_xlabel("주파수 (kHz)")
    ax.set_ylabel("세기 (dB, 0.5~5 kHz 평균 = 0)")
    ax.set_title("크롬 48 kHz → 16 kHz 변환의 주파수 모양 (백색 잡음)")
    ax.grid(alpha=.3)
    ax.legend()
    out = ROOT / "docs" / "figures" / f"{args.fig}_{args.date}.png"
    fig.tight_layout()
    fig.savefig(out, dpi=120)
    print(f"그림: {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
