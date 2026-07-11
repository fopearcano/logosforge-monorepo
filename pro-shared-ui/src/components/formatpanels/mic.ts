/**
 * Microphone capture for Dexter's Room — records from the default input,
 * downsamples to 16 kHz mono, and encodes int16 LE PCM as base64 (the shape the
 * core's /voice/transcribe endpoint expects). Web Audio only — no Node/Electron.
 */

export interface MicRecorder {
  /** Finalize: returns the captured PCM (base64) + sample rate, or null if silent. */
  stop: () => Promise<{ base64: string; sampleRate: number } | null>;
  /** Abort without producing audio (frees the mic). */
  cancel: () => void;
}

function resample(input: Float32Array, from: number, to: number): Float32Array {
  if (from === to) return input;
  const ratio = from / to;
  const len = Math.max(1, Math.round(input.length / ratio));
  const out = new Float32Array(len);
  const last = input.length - 1;
  for (let i = 0; i < len; i += 1) {
    const idx = i * ratio;
    const i0 = Math.floor(idx);
    const i1 = Math.min(i0 + 1, last);
    const frac = idx - i0;
    out[i] = (input[i0] ?? 0) * (1 - frac) + (input[i1] ?? 0) * frac;
  }
  return out;
}

function toBase64Int16(float: Float32Array): string {
  const buf = new ArrayBuffer(float.length * 2);
  const view = new DataView(buf);
  for (let i = 0; i < float.length; i += 1) {
    const s = Math.max(-1, Math.min(1, float[i] ?? 0));
    view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  const bytes = new Uint8Array(buf);
  let bin = "";
  const CHUNK = 0x8000;
  for (let i = 0; i < bytes.length; i += CHUNK) {
    bin += String.fromCharCode.apply(null, Array.from(bytes.subarray(i, i + CHUNK)) as unknown as number[]);
  }
  return btoa(bin);
}

export async function startMic(): Promise<MicRecorder> {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
  });
  const AC: typeof AudioContext = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
  let ctx: AudioContext;
  try { ctx = new AC({ sampleRate: 16000 }); } catch { ctx = new AC(); }
  const source = ctx.createMediaStreamSource(stream);
  const node = ctx.createScriptProcessor(4096, 1, 1);
  // A muted sink keeps the ScriptProcessor "pulled" (so onaudioprocess fires)
  // without routing the mic back out the speakers.
  const mute = ctx.createGain();
  mute.gain.value = 0;
  const chunks: Float32Array[] = [];
  node.onaudioprocess = (e) => { chunks.push(new Float32Array(e.inputBuffer.getChannelData(0))); };
  source.connect(node);
  node.connect(mute);
  mute.connect(ctx.destination);
  // The context is created after an await (past the user-gesture), so it can start
  // suspended — resume it or no audio is ever captured.
  if (ctx.state === "suspended") { try { await ctx.resume(); } catch { /* ignore */ } }

  const cleanup = () => {
    try { node.disconnect(); mute.disconnect(); source.disconnect(); } catch { /* ignore */ }
    stream.getTracks().forEach((t) => t.stop());
    void ctx.close();
  };

  return {
    cancel: cleanup,
    stop: async () => {
      const rate = ctx.sampleRate;
      cleanup();
      const total = chunks.reduce((n, c) => n + c.length, 0);
      if (total === 0) return null;
      const merged = new Float32Array(total);
      let o = 0;
      for (const c of chunks) { merged.set(c, o); o += c.length; }
      const pcm = resample(merged, rate, 16000);
      return { base64: toBase64Int16(pcm), sampleRate: 16000 };
    },
  };
}
