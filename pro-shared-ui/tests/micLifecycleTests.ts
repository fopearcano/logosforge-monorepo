import { startMic, type MicRecorder } from "../src/components/formatpanels/mic";

let passed = 0;
const failures: string[] = [];
const check = (label: string, condition: boolean): void => {
  if (condition) passed += 1;
  else failures.push(label);
};

interface Counters {
  trackStops: number;
  contextCloses: number;
  sourceDisconnects: number;
  processorDisconnects: number;
  gainDisconnects: number;
}

function installAudioEnvironment(failAt?: "constructor" | "processor") {
  const counters: Counters = { trackStops: 0, contextCloses: 0, sourceDisconnects: 0, processorDisconnects: 0, gainDisconnects: 0 };
  const track = { stop: () => { counters.trackStops += 1; } };
  const stream = { getTracks: () => [track] } as unknown as MediaStream;
  const source = {
    connect: () => undefined,
    disconnect: () => { counters.sourceDisconnects += 1; },
  } as unknown as MediaStreamAudioSourceNode;
  const processor = {
    onaudioprocess: null as ((event: AudioProcessingEvent) => void) | null,
    connect: () => undefined,
    disconnect: () => { counters.processorDisconnects += 1; },
  } as unknown as ScriptProcessorNode;
  const gain = {
    gain: { value: 1 },
    connect: () => undefined,
    disconnect: () => { counters.gainDisconnects += 1; },
  } as unknown as GainNode;

  class FakeAudioContext {
    sampleRate = 16000;
    state: AudioContextState = "running";
    destination = {} as AudioDestinationNode;

    constructor() {
      if (failAt === "constructor") throw new Error("audio context unavailable");
    }

    createMediaStreamSource(): MediaStreamAudioSourceNode { return source; }
    createScriptProcessor(): ScriptProcessorNode {
      if (failAt === "processor") throw new Error("processor setup failed");
      return processor;
    }
    createGain(): GainNode { return gain; }
    resume(): Promise<void> { this.state = "running"; return Promise.resolve(); }
    close(): Promise<void> { counters.contextCloses += 1; this.state = "closed"; return Promise.resolve(); }
  }

  const navigatorDescriptor = Object.getOwnPropertyDescriptor(globalThis, "navigator");
  const windowDescriptor = Object.getOwnPropertyDescriptor(globalThis, "window");
  Object.defineProperty(globalThis, "navigator", {
    configurable: true,
    value: { mediaDevices: { getUserMedia: async () => stream } },
  });
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: { AudioContext: FakeAudioContext },
  });

  const restore = () => {
    if (navigatorDescriptor) Object.defineProperty(globalThis, "navigator", navigatorDescriptor);
    else delete (globalThis as { navigator?: unknown }).navigator;
    if (windowDescriptor) Object.defineProperty(globalThis, "window", windowDescriptor);
    else delete (globalThis as { window?: unknown }).window;
  };
  return { counters, processor, restore };
}

async function withRecorder(test: (recorder: MicRecorder, env: ReturnType<typeof installAudioEnvironment>) => Promise<void>): Promise<void> {
  const env = installAudioEnvironment();
  try { await test(await startMic(), env); } finally { env.restore(); }
}

await withRecorder(async (recorder, { counters }) => {
  recorder.cancel();
  recorder.cancel();
  check("cancel stops every track exactly once", counters.trackStops === 1);
  check("cancel closes the audio context exactly once", counters.contextCloses === 1);
  check("cancel disconnects the complete graph", counters.sourceDisconnects === 1 && counters.processorDisconnects === 1 && counters.gainDisconnects === 1);
  check("stop after cancel stays inert", await recorder.stop() === null);
});

await withRecorder(async (recorder, { counters }) => {
  const result = await recorder.stop();
  check("silent stop returns no upload payload", result === null);
  check("silent stop still frees track and context", counters.trackStops === 1 && counters.contextCloses === 1);
});

await withRecorder(async (recorder, { counters, processor }) => {
  processor.onaudioprocess?.({
    inputBuffer: { getChannelData: () => new Float32Array([0.25, -0.25, 0.5]) },
  } as unknown as AudioProcessingEvent);
  const result = await recorder.stop();
  check("captured audio produces a 16 kHz payload", result?.sampleRate === 16000 && !!result.base64);
  check("captured stop frees track and context", counters.trackStops === 1 && counters.contextCloses === 1);
});

for (const failAt of ["processor", "constructor"] as const) {
  const env = installAudioEnvironment(failAt);
  let message = "";
  try { await startMic(); } catch (error) { message = error instanceof Error ? error.message : String(error); } finally { env.restore(); }
  check(`${failAt} failure propagates`, message.length > 0);
  check(`${failAt} failure releases the granted microphone`, env.counters.trackStops === 1);
  check(`${failAt} failure closes any created context`, env.counters.contextCloses === (failAt === "processor" ? 1 : 0));
}

console.log(`Microphone lifecycle tests: ${passed} passed, ${failures.length} failed`);
for (const failure of failures) console.error(`  FAIL: ${failure}`);
if (failures.length) throw new Error(`${failures.length} microphone lifecycle test(s) failed`);
console.log("MICROPHONE LIFECYCLE TESTS: PASS");
