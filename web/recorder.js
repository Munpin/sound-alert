// recorder.js
// 녹음(16 kHz 조각 모으기), wav 만들기, 파일 이름과 sessions.csv 한 줄(회차 정보) 만들기, 화면 켜 두기.
// audio-input.js가 준 16 kHz 신호를 그대로 저장한다. 저장할 때 샘플레이트를 다시 바꾸지 않는다.

import { TARGET_RATE, CLIP_LEVEL } from './audio-input.js';

// ---------------------------------------------------------------------------
// 녹음기: 조각을 모아 하나의 신호로 만든다
// ---------------------------------------------------------------------------
export class Recorder {
  constructor(sampleRate = TARGET_RATE) {
    this.sampleRate = sampleRate;
    this.chunks = [];
    this.length = 0;
    this.clipped = 0;     // 잘린 샘플 수
    this.peak = 0;        // 가장 큰 값(0~1)
    this.active = false;
  }

  start() {
    this.chunks = [];
    this.length = 0;
    this.clipped = 0;
    this.peak = 0;
    this.active = true;
  }

  /** audio-input.js의 onChunk에서 부른다. 녹음 중일 때만 쌓는다. */
  push(chunk) {
    if (!this.active) return;
    this.chunks.push(chunk);
    this.length += chunk.length;
    for (let i = 0; i < chunk.length; i++) {
      const a = Math.abs(chunk[i]);
      if (a > this.peak) this.peak = a;
      if (a >= CLIP_LEVEL) this.clipped++;
    }
  }

  /** 경과 시간(초). 받은 샘플 수로 계산하므로 정확하다. */
  get seconds() {
    return this.length / this.sampleRate;
  }

  /** 녹음을 멈추고 전체 신호(Float32Array)를 돌려준다. */
  stop() {
    this.active = false;
    const all = new Float32Array(this.length);
    let off = 0;
    for (const c of this.chunks) {
      all.set(c, off);
      off += c.length;
    }
    this.chunks = [];
    return all;
  }
}

// ---------------------------------------------------------------------------
// wav 만들기: 16 kHz, 모노, 16비트 PCM
// ---------------------------------------------------------------------------
export function encodeWav(samples, sampleRate = TARGET_RATE) {
  const numChannels = 1;
  const bytesPerSample = 2;
  const dataSize = samples.length * bytesPerSample;
  const buf = new ArrayBuffer(44 + dataSize);
  const v = new DataView(buf);
  const str = (off, s) => { for (let i = 0; i < s.length; i++) v.setUint8(off + i, s.charCodeAt(i)); };

  str(0, 'RIFF');
  v.setUint32(4, 36 + dataSize, true);
  str(8, 'WAVE');
  str(12, 'fmt ');
  v.setUint32(16, 16, true);                                   // fmt 덩어리 크기
  v.setUint16(20, 1, true);                                    // 1 = PCM
  v.setUint16(22, numChannels, true);
  v.setUint32(24, sampleRate, true);
  v.setUint32(28, sampleRate * numChannels * bytesPerSample, true); // 초당 바이트
  v.setUint16(32, numChannels * bytesPerSample, true);
  v.setUint16(34, 8 * bytesPerSample, true);                   // 16비트
  str(36, 'data');
  v.setUint32(40, dataSize, true);

  // -1~1 실수 → -32768~32767 정수. 범위를 넘는 값은 끝값으로 자른다.
  let off = 44;
  for (let i = 0; i < samples.length; i++) {
    let s = samples[i];
    if (s > 1) s = 1; else if (s < -1) s = -1;
    v.setInt16(off, s < 0 ? Math.round(s * 32768) : Math.round(s * 32767), true);
    off += 2;
  }
  return new Blob([buf], { type: 'audio/wav' });
}

// ---------------------------------------------------------------------------
// 파일 이름과 메타데이터 (설계서 4절)
// ---------------------------------------------------------------------------
export const CLASSES = ['doorbell', 'knock', 'baby_cry', 'siren', 'horn', 'other'];
export const PLACES = ['desk', 'bed', 'bath', 'entrance', 'kitchen', 'outside'];
export const PHONE_STATES = ['desk', 'hand', 'blanket'];
export const BACKGROUNDS = ['quiet', 'music', 'speech', 'fan', 'water', 'washer', 'tv', 'street', 'bus', 'walking'];
export const DEVICE = 'phone';
export const META_HEADER =
  'file,class,source,group_id,split,place,background,phone_state,device,date,license,note';

/** 오늘 날짜 MMDD (휴대폰 시각 기준) */
export function todayMMDD(d = new Date()) {
  return String(d.getMonth() + 1).padStart(2, '0') + String(d.getDate()).padStart(2, '0');
}

/** 오늘 날짜 YYYY-MM-DD (sessions.csv의 date 칸) */
export function todayISO(d = new Date()) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

/** 회차 번호 → 's01' */
export function sessionId(n) {
  return 's' + String(n).padStart(2, '0');
}

/** 파일 이름에 넣을 수 있는 값인지: 영문 소문자, 숫자, 밑줄만 */
export function isSafePart(s) {
  return /^[a-z0-9_]+$/.test(s);
}

/** 장소는 밑줄도 빼고 영문 소문자·숫자만 (파일 이름을 '_'로 다시 나눌 수 있게) */
export function isSafePlace(s) {
  return /^[a-z0-9]+$/.test(s);
}

/** 회차 ID (분할 단위). 예: phone_1126_s01 */
export function groupId({ date, session }) {
  return `${DEVICE}_${date}_${sessionId(session)}`;
}

/** 기본 파일 이름 (확장자 없음). 예: doorbell_1126_s01_desk_phone */
export function baseName({ cls, date, session, place }) {
  return `${cls}_${date}_${sessionId(session)}_${place}_${DEVICE}`;
}

/**
 * 이미 저장한 이름과 겹치면 _t2, _t3 …을 붙인다.
 * @param {string} base 확장자 없는 이름
 * @param {Set<string>} used 이미 저장한 파일 이름(.wav 포함)
 */
export function uniqueFileName(base, used) {
  if (!used.has(base + '.wav')) return { name: base + '.wav', take: 1 };
  for (let t = 2; ; t++) {
    const name = `${base}_t${t}.wav`;
    if (!used.has(name)) return { name, take: t };
  }
}

/** CSV 칸 하나: 쉼표·따옴표·줄바꿈이 있으면 따옴표로 감싼다 */
function csvField(s) {
  s = String(s ?? '');
  return /[",\n\r]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
}

/** data/sessions.csv에 붙여 넣을 한 줄 (회차 정보. data/meta.csv는 build_meta.py가 만든다) */
export function metaRow({ file, cls, date, session, place, background, phoneState, isoDate, note }) {
  return [
    file,
    cls,
    'own',                       // source: 직접 녹음
    groupId({ date, session }),  // group_id: 회차 ID
    '',                          // split: 나중에 정함
    place,
    background,
    phoneState,
    DEVICE,
    isoDate,
    'own',                       // license: 직접 녹음
    note,
  ].map(csvField).join(',');
}

// ---------------------------------------------------------------------------
// 다운로드
// ---------------------------------------------------------------------------
export function downloadBlob(blob, fileName) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = fileName;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}

// ---------------------------------------------------------------------------
// 화면 켜 두기 (Wake Lock). 녹음하는 동안 화면이 꺼지지 않게 한다.
// 다른 앱으로 갔다 오면 풀리므로, 돌아왔을 때 다시 요청한다.
// ---------------------------------------------------------------------------
export class ScreenWakeLock {
  constructor(onChange) {
    this.sentinel = null;
    this.wanted = false;
    this.onChange = onChange || (() => {});
    document.addEventListener('visibilitychange', () => {
      if (this.wanted && document.visibilityState === 'visible') this._request();
    });
  }

  get supported() {
    return 'wakeLock' in navigator;
  }

  async on() {
    this.wanted = true;
    await this._request();
  }

  async off() {
    this.wanted = false;
    if (this.sentinel) {
      try { await this.sentinel.release(); } catch (_) {}
      this.sentinel = null;
    }
    this.onChange(false);
  }

  async _request() {
    if (!this.supported) { this.onChange(false, '지원 안 함'); return; }
    try {
      this.sentinel = await navigator.wakeLock.request('screen');
      this.onChange(true);
      this.sentinel.addEventListener('release', () => {
        this.sentinel = null;
        this.onChange(false);
      });
    } catch (e) {
      this.onChange(false, String(e && e.message ? e.message : e));
    }
  }
}
