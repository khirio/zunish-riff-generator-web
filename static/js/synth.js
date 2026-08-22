const SOUNDFONT_URL = "/soundfonts/FluidR3Mono_GM.sf3";
const RENDER_BUFFER_FRAMES = 2048;

let scriptsLoadedPromise = null;

function loadScript(src) {
  return new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = src;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error(`failed to load script: ${src}`));
    document.head.appendChild(script);
  });
}

function ensureScriptsLoaded() {
  if (!scriptsLoadedPromise) {
    scriptsLoadedPromise = loadScript("vendor/libfluidsynth-2.4.6-with-libsndfile.js")
      .then(() => loadScript("vendor/js-synthesizer.js"))
      .then(() => window.JSSynth.waitForReady());
  }
  return scriptsLoadedPromise;
}

/**
 * Create (once per page load) a js-synthesizer Synthesizer + Sequencer pair,
 * loaded with the bundled soundfont and connected to `outputNode`. See
 * WEB_DESIGN.md 8.1/8.3 for why the ScriptProcessorNode-based `Synthesizer`
 * (not `AudioWorkletNodeSynthesizer`) and the tick-based `ISequencer` are
 * used.
 */
export async function createSynthEngine(audioContext, outputNode) {
  await ensureScriptsLoaded();
  const JSSynth = window.JSSynth;

  const synth = new JSSynth.Synthesizer();
  synth.init(audioContext.sampleRate);
  const node = synth.createAudioNode(audioContext, RENDER_BUFFER_FRAMES);
  node.connect(outputNode);

  const soundfontResponse = await fetch(SOUNDFONT_URL);
  if (!soundfontResponse.ok) {
    throw new Error(`failed to fetch soundfont: ${soundfontResponse.status} ${soundfontResponse.statusText}`);
  }
  const soundfontBuffer = await soundfontResponse.arrayBuffer();
  await synth.loadSFont(soundfontBuffer);

  const sequencer = await JSSynth.Synthesizer.createSequencer();
  await sequencer.registerSynthesizer(synth);

  return { synth, sequencer };
}
