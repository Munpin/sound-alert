// audio-input.js
// 마이크 → 16 kHz 모노 신호.
// 녹음 페이지와 알림 앱이 이 파일을 똑같이 쓴다. 그래야 학습 데이터와 실제 입력이 같은 경로를 지난다.
//
// 흐름: getUserMedia(통화용 처리 3가지 끔) → AudioContext → AudioWorklet → 16 kHz Float32 조각(chunk)
//   - 방식 'browser': AudioContext를 16 kHz로 만들고, 브라우저가 마이크 신호를 16 kHz로 바꿔 준다.
//   - 방식 'js'     : 16 kHz AudioContext가 안 되면 원래 샘플레이트(보통 48 kHz)로 받아
//                     AudioWorklet 안에서 JavaScript로 16 kHz로 바꾼다(윈도 싱크 보간).
// 어느 방식이든 onChunk로 나가는 값은 모델이 받을 16 kHz 신호 그대로다.

export const TARGET_RATE = 16000;

// 통화용 처리(에코 제거, 잡음 제거, 자동 음량)를 모두 끄고 채널 1개로 요청한다.
// 켜 두면 초인종·노크 같은 소리가 깎일 수 있다(설계서 3절 '마이크 설정').
export const MIC_CONSTRAINTS = {
  audio: {
    echoCancellation: false,
    noiseSuppression: false,
    autoGainControl: false,
    channelCount: 1,
  },
  video: false,
};

// ---------------------------------------------------------------------------
// AudioWorklet 처리기 코드.
// AudioWorklet은 소리를 별도 스레드에서 128개 샘플씩 받아 처리하는 브라우저 기능이다.
// 파일을 하나 더 두지 않으려고 문자열로 만들어 Blob 주소로 불러온다.
// (테스트에서도 이 문자열을 그대로 실행해 변환 품질을 확인한다.)
// ---------------------------------------------------------------------------
export const WORKLET_SOURCE = String.raw`
class Capture16kProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super();
    const o = (options && options.processorOptions) || {};
    this.outRate = o.targetRate || 16000;
    this.inRate = o.inputRate || sampleRate; // sampleRate: worklet 전역값(AudioContext 샘플레이트)
    this.chunkSize = o.chunkSize || 800;
    this.out = new Float32Array(this.chunkSize);
    this.outLen = 0;
    this.resample = Math.abs(this.inRate - this.outRate) > 0.5;
    if (this.resample) this.initResampler();
  }

  // 윈도 싱크 저역통과 + 보간. 8 kHz(새 샘플레이트의 절반) 위 소리가 접혀 들어오지 않도록
  // 7.2 kHz 근처부터 깎는다. 커널은 미리 표로 계산해 두고 선형 보간으로 찾는다.
  initResampler() {
    this.step = this.inRate / this.outRate;          // 출력 1개당 입력 몇 개 (48k→16k면 3)
    const fc = (0.45 * this.outRate) / this.inRate;  // 차단 주파수 (입력 샘플 기준, 0.45*16k = 7.2 kHz)
    this.hw = Math.ceil(24 * this.step);             // 커널 반쪽 길이(입력 샘플 수)
    this.res = 256;                                  // 입력 샘플 1개당 표 칸 수
    const beta = 8.0;                                // Kaiser 창 모양
    const n = this.hw * this.res + 2;
    this.tab = new Float32Array(n);
    const i0b = Capture16kProcessor.besselI0(beta);
    for (let i = 0; i < n; i++) {
      const t = i / this.res;
      if (t >= this.hw) { this.tab[i] = 0; continue; }
      const x = 2 * fc * t;
      const sinc = x === 0 ? 1 : Math.sin(Math.PI * x) / (Math.PI * x);
      const r = t / this.hw;
      const win = Capture16kProcessor.besselI0(beta * Math.sqrt(1 - r * r)) / i0b;
      this.tab[i] = 2 * fc * sinc * win;
    }
    // 입력 보관함. 앞에 hw개의 0을 깔아 두면 처음 출력도 같은 식으로 계산된다.
    this.buf = new Float32Array(Math.max(8192, 4 * this.hw + 1024));
    this.bufLen = this.hw;
    this.t = this.hw;  // 다음 출력 샘플의 위치(보관함 안 좌표, 소수 포함)
  }

  static besselI0(x) {
    let sum = 1, term = 1;
    for (let k = 1; k < 50; k++) {
      term *= (x / (2 * k)) * (x / (2 * k));
      sum += term;
      if (term < 1e-12 * sum) break;
    }
    return sum;
  }

  emit(v) {
    this.out[this.outLen++] = v;
    if (this.outLen === this.chunkSize) {
      this.port.postMessage(this.out, [this.out.buffer]);
      this.out = new Float32Array(this.chunkSize);
      this.outLen = 0;
    }
  }

  pushResample(ch) {
    // 1) 보관함에 새 입력 붙이기 (자리가 모자라면 키움)
    if (this.bufLen + ch.length > this.buf.length) {
      const bigger = new Float32Array((this.bufLen + ch.length) * 2);
      bigger.set(this.buf.subarray(0, this.bufLen));
      this.buf = bigger;
    }
    this.buf.set(ch, this.bufLen);
    this.bufLen += ch.length;

    // 2) 오른쪽 hw개 입력이 모두 있는 위치까지 출력 만들기
    const hw = this.hw, res = this.res, tab = this.tab, buf = this.buf;
    while (this.t + hw < this.bufLen) {
      const t = this.t;
      const k0 = Math.ceil(t - hw), k1 = Math.floor(t + hw);
      let acc = 0;
      for (let k = k0; k <= k1; k++) {
        const d = Math.abs(t - k) * res;
        const i = d | 0;
        const w = tab[i] + (tab[i + 1] - tab[i]) * (d - i);
        acc += buf[k] * w;
      }
      this.emit(acc);
      this.t += this.step;
    }

    // 3) 더 안 쓸 앞부분 버리기
    const drop = Math.floor(this.t - hw) - 1;
    if (drop > 0) {
      buf.copyWithin(0, drop, this.bufLen);
      this.bufLen -= drop;
      this.t -= drop;
    }
  }

  process(inputs) {
    const input = inputs[0];
    if (!input || input.length === 0) return true; // 아직 마이크가 연결되지 않음
    const ch = input[0]; // channelCountMode 'explicit', 채널 1 → 브라우저가 모노로 섞어 준다
    if (this.resample) {
      this.pushResample(ch);
    } else {
      for (let i = 0; i < ch.length; i++) this.emit(ch[i]);
    }
    return true;
  }
}
registerProcessor('capture-16k', Capture16kProcessor);
`;

// ---------------------------------------------------------------------------
// 마이크 켜기
// ---------------------------------------------------------------------------

/**
 * 마이크를 켜고 16 kHz 모노 신호를 조각으로 보낸다. 반드시 버튼 클릭 안에서 불러야 한다.
 * @param {object} opt
 * @param {(chunk: Float32Array) => void} opt.onChunk  16 kHz 조각을 받을 함수
 * @param {number} [opt.chunkSize=800]                 조각 길이(샘플). 800개 = 50 ms
 * @param {boolean} [opt.forceJs=false]                시험용: 브라우저 변환을 건너뛰고 JS 변환 사용
 * @param {() => void} [opt.onEnded]                   마이크가 끊겼을 때(다른 앱이 가져감 등)
 */
export async function openMicrophone({ onChunk, chunkSize = 800, forceJs = false, onEnded } = {}) {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    throw new Error('이 브라우저는 마이크를 쓸 수 없습니다. https 주소인지 확인하세요.');
  }
  const stream = await navigator.mediaDevices.getUserMedia(MIC_CONSTRAINTS);
  const track = stream.getAudioTracks()[0];
  const settings = track.getSettings();
  if (onEnded) track.addEventListener('ended', onEnded);

  // 1) 16 kHz AudioContext 시도 → 안 되면 기본 AudioContext + JS 변환
  let context = null, source = null, method = 'browser', fallbackReason = '';
  if (!forceJs) {
    try {
      context = new AudioContext({ sampleRate: TARGET_RATE, latencyHint: 'interactive' });
      if (context.sampleRate !== TARGET_RATE) throw new Error(`요청 16000, 실제 ${context.sampleRate}`);
      source = context.createMediaStreamSource(stream);
    } catch (e) {
      fallbackReason = String(e && e.message ? e.message : e);
      if (context) context.close().catch(() => {});
      context = null; source = null;
    }
  } else {
    fallbackReason = '시험용으로 JS 변환을 강제함(?resample=js)';
  }
  if (!context) {
    method = 'js';
    context = new AudioContext({ latencyHint: 'interactive' });
    source = context.createMediaStreamSource(stream);
  }

  // 2) AudioWorklet 불러오기
  const url = URL.createObjectURL(new Blob([WORKLET_SOURCE], { type: 'application/javascript' }));
  try {
    await context.audioWorklet.addModule(url);
  } finally {
    URL.revokeObjectURL(url);
  }
  const node = new AudioWorkletNode(context, 'capture-16k', {
    numberOfInputs: 1,
    numberOfOutputs: 1,
    outputChannelCount: [1],
    channelCount: 1,
    channelCountMode: 'explicit',
    channelInterpretation: 'speakers',
    processorOptions: { targetRate: TARGET_RATE, chunkSize },
  });
  node.port.onmessage = (e) => onChunk && onChunk(e.data);

  // 3) 연결: 마이크 → worklet → 음량 0 → 스피커
  //    (스피커 쪽에 이어 둬야 브라우저가 worklet을 계속 돌린다. 음량 0이라 소리는 나지 않는다.)
  const mute = context.createGain();
  mute.gain.value = 0;
  source.connect(node);
  node.connect(mute);
  mute.connect(context.destination);
  await context.resume();

  return {
    stream,
    track,
    settings,                       // track.getSettings() 결과 (실제 적용된 값)
    method,                         // 'browser' | 'js'
    methodLabel: method === 'browser'
      ? `브라우저 변환 (AudioContext ${context.sampleRate} Hz)`
      : `JavaScript 변환 (${context.sampleRate} Hz → ${TARGET_RATE} Hz)`,
    fallbackReason,                 // JS 변환으로 간 이유 (browser면 빈 문자열)
    contextRate: context.sampleRate,
    outputRate: TARGET_RATE,
    context,
    async stop() {
      node.port.onmessage = null;
      try { source.disconnect(); node.disconnect(); mute.disconnect(); } catch (_) {}
      stream.getTracks().forEach((t) => t.stop());
      await context.close().catch(() => {});
    },
  };
}

// ---------------------------------------------------------------------------
// 음량 재기 (음량 막대, 클리핑 경고에 씀)
// ---------------------------------------------------------------------------

// 이 값 이상이면 '잘림(클리핑)'으로 본다. 1.0이 디지털 최댓값이다.
export const CLIP_LEVEL = 0.99;

/** 조각 하나의 RMS(평균 세기), 최댓값, 잘린 샘플 수 */
export function measureLevel(chunk) {
  let sum = 0, peak = 0, clipped = 0;
  for (let i = 0; i < chunk.length; i++) {
    const a = Math.abs(chunk[i]);
    sum += a * a;
    if (a > peak) peak = a;
    if (a >= CLIP_LEVEL) clipped++;
  }
  const rms = Math.sqrt(sum / Math.max(1, chunk.length));
  return { rms, peak, clipped };
}

/** 0~1 세기를 dBFS로 (0 dBFS가 최댓값, -60 아래는 -60으로) */
export function toDb(x) {
  return Math.max(-60, 20 * Math.log10(Math.max(x, 1e-6)));
}
