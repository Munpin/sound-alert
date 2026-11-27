"""공개 데이터를 휴대폰 경로와 같은 모양의 16 kHz 모노로 바꾸는 공용 함수.

  parse_wav(bytes)        wav 바이트 → (float64 [샘플, 채널], 샘플레이트). 16/24/32비트 정수, 32비트 실수 지원
  to_phone_16k(x, sr)     모노로 섞기 → soxr로 48 kHz → 크롬 모양 필터 → 16 kHz
  best_window(y, sec)     가장 소리가 큰 2초 창 고르기
  write_wav16(path, y)    16 kHz 모노 16비트 wav 저장

크롬 모양 필터 (2-5 결정, 사용자 승인 2026-11-27)
  휴대폰 크롬은 48 kHz → 16 kHz로 바꿀 때 6.4 kHz부터 완만하게 높은 소리를 줄이고, soxr는 7.56 kHz까지 평평하다.
  이 차이가 '휴대폰 녹음 = 초인종·노크' 지름길이 되지 않도록, 공개 데이터는 soxr 뒤에 크롬 특성을 흉내 내는
  선형 위상 FIR을 48 kHz에서 씌운 뒤 16 kHz로 줄인다. 특성 곡선은 train/chrome_response.json (PC 크롬 158 실측).
  직접 녹음과 재녹음은 이미 크롬을 거쳤으므로 씌우지 않는다.
"""

import json
import struct
import wave
from functools import lru_cache
from pathlib import Path

import numpy as np
import soxr

SR = 16000



def parse_wav(data: bytes):
    """RIFF wav 파싱 (fmt·data 덩어리만). 반환 (x [n, ch] float64 -1~1, sr)"""
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise ValueError("wav가 아님")
    pos, fmt, raw = 12, None, None
    while pos + 8 <= len(data):
        cid, size = data[pos:pos + 4], struct.unpack("<I", data[pos + 4:pos + 8])[0]
        body = data[pos + 8:pos + 8 + size]
        if cid == b"fmt ":
            fmt = struct.unpack("<HHIIHH", body[:16])
            if fmt[0] == 0xFFFE and len(body) >= 26:          # WAVE_FORMAT_EXTENSIBLE → 실제 형식
                fmt = (struct.unpack("<H", body[24:26])[0],) + fmt[1:]
        elif cid == b"data":
            raw = body
        pos += 8 + size + (size & 1)
    if fmt is None or raw is None:
        raise ValueError("fmt 또는 data 덩어리가 없음")
    tag, ch, sr, _, _, bits = fmt
    n = len(raw) // (ch * bits // 8)
    raw = raw[: n * ch * bits // 8]
    if tag == 1 and bits == 16:
        x = np.frombuffer(raw, "<i2").astype(np.float64) / 32768.0
    elif tag == 1 and bits == 24:
        b = np.frombuffer(raw, np.uint8).reshape(-1, 3)
        v = (b[:, 0].astype(np.int32) | (b[:, 1].astype(np.int32) << 8) | (b[:, 2].astype(np.int32) << 16))
        v = np.where(v & 0x800000, v - 0x1000000, v)
        x = v.astype(np.float64) / 8388608.0
    elif tag == 1 and bits == 32:
        x = np.frombuffer(raw, "<i4").astype(np.float64) / 2147483648.0
    elif tag == 3 and bits == 32:
        x = np.frombuffer(raw, "<f4").astype(np.float64)
    elif tag == 1 and bits == 8:
        x = (np.frombuffer(raw, np.uint8).astype(np.float64) - 128) / 128.0
    else:
        raise ValueError(f"지원하지 않는 wav 형식: tag {tag}, {bits}비트")
    return x.reshape(-1, ch), sr


MID = 48000          # 휴대폰 마이크와 같은 중간 샘플레이트
FIR48_TAPS = 1023
TAIL_DB_PER_KHZ = 40.0  # 8 kHz 위는 크롬 실측이 없어 8 kHz 값에서 kHz당 40 dB씩 줄인다(최저 -90 dB)


@lru_cache(maxsize=1)
def chrome_fir48():
    """48 kHz에서 쓰는 선형 위상 FIR. 0~8 kHz는 chrome_response.json(크롬 실측), 8 kHz 위는 급하게 줄임.
    48 kHz에서 걸러 3개마다 1개를 고르면 크롬처럼 '48 kHz → 16 kHz'를 한 번에 흉내 낸다
    (soxr로 16 kHz를 먼저 만들면 7.6 kHz 위가 이미 끊겨 크롬의 7.5~8 kHz 모양을 못 만든다)."""
    d = json.loads(Path(__file__).with_name("chrome_response.json").read_text(encoding="utf-8"))
    nfft = 16384
    grid = np.fft.rfftfreq(nfft, 1 / MID)
    db = np.interp(grid, d["freq_hz"], d["gain_db"])
    edge = np.interp(SR / 2, d["freq_hz"], d["gain_db"])
    over = grid > SR / 2
    db[over] = np.maximum(edge - TAIL_DB_PER_KHZ * (grid[over] - SR / 2) / 1000, -90.0)
    h = np.fft.irfft(10 ** (db / 20), nfft)
    h = np.roll(h, FIR48_TAPS // 2)[:FIR48_TAPS] * np.hanning(FIR48_TAPS)
    return h / h.sum()


def fft_filter(x, h):
    """선형 위상 FIR을 FFT로 걸고 지연을 없앤다(입력과 같은 길이)"""
    n = len(x) + len(h) - 1
    nfft = 1 << (n - 1).bit_length()
    y = np.fft.irfft(np.fft.rfft(x, nfft) * np.fft.rfft(h, nfft), nfft)[:n]
    d = (len(h) - 1) // 2
    return y[d:d + len(x)]


def to_phone_16k(x, sr, chrome=True):
    """[n, ch] 또는 [n] → 16 kHz 모노 float64.
    chrome=True(기본): soxr로 48 kHz → 크롬 모양 FIR → 3개마다 1개 (휴대폰 경로 흉내)
    chrome=False: soxr(VHQ)로 바로 16 kHz"""
    x = np.asarray(x, dtype=np.float64)
    if x.ndim == 2:
        x = x.mean(axis=1)
    if not chrome:
        return soxr.resample(x, sr, SR, quality="VHQ") if sr != SR else x.copy()
    x48 = soxr.resample(x, sr, MID, quality="VHQ") if sr != MID else x
    return fft_filter(x48, chrome_fir48())[::MID // SR].copy()


def frame_rms_db(y, win=400, hop=160):
    if len(y) < win:
        y = np.pad(y, (0, win - len(y)))
    f = np.lib.stride_tricks.sliding_window_view(y, win)[::hop]
    return 10 * np.log10((f ** 2).mean(axis=1) + 1e-12)


def best_window(y, sec=2.0, hop_sec=0.1):
    """가장 에너지가 큰 sec초 창. 반환 (시작 샘플, 창 RMS dBFS). 신호가 sec보다 짧으면 None"""
    n = int(sec * SR)
    if len(y) < n:
        return None
    c = np.concatenate([[0.0], np.cumsum(y ** 2)])
    starts = np.arange(0, len(y) - n + 1, int(hop_sec * SR))
    e = c[starts + n] - c[starts]
    i = int(starts[np.argmax(e)])
    return i, float(10 * np.log10(e.max() / n + 1e-12))


def write_wav16(path, y):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = np.clip(np.round(np.asarray(y) * 32767), -32768, 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
