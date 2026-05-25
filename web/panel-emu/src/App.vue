<script setup>
import { ref, reactive, computed } from 'vue';
import Panel from './components/Panel.vue';
import { SCENES } from './demo-scenes.js';

// ───────── Panel state (mirrors what the firmware would render) ─────────
const view = ref('demo');             // 'demo' | 'briefing' | 'grid'
const status = ref('ready');
const lines = reactive(Array.from({ length: 8 }, () => ({ text: '', role: 'plain' })));
const color = reactive({ r: 40, g: 40, b: 50 });
const briefing = reactive({ testing: '', mechanism: '', watch: '', expected: '' });
const grid = reactive({
  cols: 6, rows: 6,
  pos:   { x: 0, y: 0 },
  ghost: null,
  flash: '',
});

// How long to show each scene's briefing before the demo starts.
const BRIEFING_HOLD_MS = 7500;

// ───────── Transcript log (full conversation, no length truncation) ─────────
const transcript = ref([]);

function applyStep(step) {
  switch (step.kind) {
    case 'clear_screen':
      for (let i = 0; i < 8; i++) {
        lines[i].text = '';
        lines[i].role = 'plain';
      }
      Object.assign(color, { r: 40, g: 40, b: 50 });
      break;
    case 'clear_narration':
      for (let i = 0; i < 3; i++) {
        lines[i].text = '';
        lines[i].role = 'plain';
      }
      break;
    case 'view':
      view.value = step.view;
      break;
    case 'set_status':
      status.value = step.text;
      break;
    case 'display_text':
    case 'narrate':
      if (lines[step.line]) {
        lines[step.line].text = step.text;
        lines[step.line].role = step.role || 'plain';
      }
      break;
    case 'set_color':
      Object.assign(color, { r: step.r, g: step.g, b: step.b });
      break;
    // grid-mode steps
    case 'pos':
      grid.pos = { x: step.x, y: step.y };
      break;
    case 'move':
      grid.pos = {
        x: Math.max(0, Math.min(grid.cols - 1, grid.pos.x + (step.dx || 0))),
        y: Math.max(0, Math.min(grid.rows - 1, grid.pos.y + (step.dy || 0))),
      };
      grid.flash = 'ok';
      setTimeout(() => { grid.flash = ''; }, 250);
      break;
    case 'try_move':
      // attempted move that the bridge will deny — show ghost + flash, no pos change
      grid.ghost = {
        x: Math.min(grid.cols, grid.pos.x + (step.dx || 0)),
        y: Math.min(grid.rows, grid.pos.y + (step.dy || 0)),
      };
      grid.flash = 'err';
      break;
    case 'ghost':
      if (step.clear) grid.ghost = null;
      else grid.ghost = { x: step.x, y: step.y };
      break;
    case 'flash':
      grid.flash = step.flash;
      break;
    case 'note':
    case 'pause':
      break;
  }
  // push to transcript
  if (['set_status', 'display_text', 'narrate', 'set_color', 'clear_screen',
       'note', 'move', 'try_move', 'ghost', 'flash', 'pos'].includes(step.kind)) {
    transcript.value.push({ ...step, ts: Date.now() });
  }
}

// ───────── Player ─────────
const running = ref(false);
const currentScene = ref(-1);
const speed = ref(1.0);   // 1.0 = real-time. 2.0 = 2× faster, 0.5 = half.

async function playStep(step) {
  if (step.kind === 'pause') {
    await new Promise((r) => setTimeout(r, step.ms / speed.value));
  } else {
    applyStep(step);
  }
}

async function playSceneBriefing(scene) {
  // Switch the panel to briefing view, populate fields, hold N ms.
  view.value = 'briefing';
  status.value = scene.tag;
  Object.assign(briefing, scene.briefing || {});
  // Clear any leftover state visible at the edges (color chip stays per
  // the previous scene's final state, intentionally — visual continuity).
  await new Promise((r) => setTimeout(r, BRIEFING_HOLD_MS / speed.value));
}

async function runDemo() {
  if (running.value) return;
  running.value = true;
  transcript.value = [];
  status.value = 'starting…';
  for (let i = 0; i < 8; i++) { lines[i].text = ''; lines[i].role = 'plain'; }
  view.value = 'demo';

  for (let s = 0; s < SCENES.length; s++) {
    currentScene.value = s;
    if (!running.value) break;
    // Briefing first — sets up the audience for what the scene proves.
    if (SCENES[s].briefing) {
      await playSceneBriefing(SCENES[s]);
      if (!running.value) break;
    }
    // Then switch to demo view and play the actual events.
    view.value = 'demo';
    for (const step of SCENES[s].steps) {
      if (!running.value) break;
      await playStep(step);
    }
    if (!running.value) break;
  }
  currentScene.value = -1;
  running.value = false;
}

function stopDemo() {
  running.value = false;
}

async function playSingleScene(i) {
  if (running.value) return;
  running.value = true;
  currentScene.value = i;
  transcript.value = [];
  if (SCENES[i].briefing) {
    await playSceneBriefing(SCENES[i]);
  }
  view.value = 'demo';
  for (const step of SCENES[i].steps) {
    if (!running.value) break;
    await playStep(step);
  }
  running.value = false;
  currentScene.value = -1;
}

// Pretty transcript classes
const roleStyle = {
  user:    'border-l-2 border-role-user    pl-2',
  llm:     'border-l-2 border-role-llm     pl-2',
  dcp_ok:  'border-l-2 border-role-dcp_ok  pl-2',
  dcp_err: 'border-l-2 border-role-dcp_err pl-2',
  dcp_req: 'border-l-2 border-role-dcp_req pl-2',
  plain:   'border-l-2 border-zinc-700     pl-2',
};

const transcriptItems = computed(() => transcript.value.slice().reverse());
</script>

<template>
  <div class="min-h-screen flex flex-col items-stretch text-zinc-100 p-6 gap-6">
    <!-- top bar -->
    <header class="flex items-center justify-between">
      <div>
        <h1 class="text-xl font-semibold tracking-tight">DCP Panel Emulator</h1>
        <p class="text-sm text-zinc-400">
          480×480 LCD preview · iterate UI in browser, port to LVGL when locked in.
        </p>
      </div>
      <div class="flex items-center gap-3">
        <label class="text-xs text-zinc-400">speed</label>
        <input
          type="range" min="0.25" max="4" step="0.25" v-model.number="speed"
          class="w-32"
        />
        <span class="text-xs text-zinc-400 w-10">{{ speed }}x</span>
        <button
          @click="runDemo" :disabled="running"
          class="px-3 py-1.5 rounded bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-sm"
        >▶ Run full demo</button>
        <button
          @click="stopDemo" :disabled="!running"
          class="px-3 py-1.5 rounded bg-zinc-700 hover:bg-zinc-600 disabled:opacity-50 text-sm"
        >■ Stop</button>
      </div>
    </header>

    <!-- main grid: panel + transcript + scene list -->
    <main class="flex gap-6 items-start">
      <!-- the 480×480 emulator inside a bezel -->
      <section class="shrink-0">
        <div class="p-3 rounded-2xl bg-zinc-900 ring-1 ring-zinc-800 shadow-2xl">
          <Panel
            :view="view"
            :status="status"
            :lines="lines"
            :color="color"
            :briefing="briefing"
            :grid="grid"
          />
        </div>
        <p class="text-xs text-zinc-500 mt-2 text-center">
          480 × 480 · ST7701S · LVGL 8.3.5
        </p>
      </section>

      <!-- live transcript -->
      <section class="flex-1 min-w-0">
        <h2 class="text-sm uppercase tracking-wide text-zinc-400 mb-2">
          live transcript
        </h2>
        <div class="bg-zinc-900 ring-1 ring-zinc-800 rounded-lg p-3 h-[460px] overflow-y-auto text-sm font-mono leading-relaxed">
          <div v-if="!transcript.length" class="text-zinc-500 italic">
            Press “Run full demo” to start. Each line below is one DCP event.
          </div>
          <ul class="space-y-1">
            <li
              v-for="(ev, idx) in transcriptItems"
              :key="idx"
              :class="roleStyle[ev.role] || roleStyle.plain"
            >
              <span class="text-zinc-500 text-xs mr-2">{{ ev.kind }}</span>
              <template v-if="ev.kind === 'set_status'">
                <span class="text-zinc-200">{{ ev.text }}</span>
              </template>
              <template v-else-if="ev.kind === 'display_text'">
                <span class="text-zinc-400">L{{ ev.line }} [{{ ev.role }}]</span>
                <span class="text-zinc-100 ml-2">{{ ev.text }}</span>
              </template>
              <template v-else-if="ev.kind === 'set_color'">
                <span class="text-zinc-400">rgb</span>
                <span class="ml-1 inline-block w-3 h-3 align-middle ring-1 ring-zinc-600"
                      :style="{ backgroundColor: `rgb(${ev.r},${ev.g},${ev.b})` }" />
                <span class="text-zinc-300 ml-1">({{ ev.r }},{{ ev.g }},{{ ev.b }})</span>
              </template>
              <template v-else-if="ev.kind === 'clear_screen'">
                <span class="text-zinc-500 italic">— clear —</span>
              </template>
            </li>
          </ul>
        </div>
      </section>

      <!-- scene list -->
      <aside class="w-72 shrink-0">
        <h2 class="text-sm uppercase tracking-wide text-zinc-400 mb-2">
          scenes
        </h2>
        <ul class="space-y-2">
          <li
            v-for="(s, i) in SCENES"
            :key="s.tag"
            class="rounded-lg ring-1 px-3 py-2 bg-zinc-900 transition"
            :class="currentScene === i ? 'ring-emerald-500' : 'ring-zinc-800'"
          >
            <div class="flex items-center justify-between">
              <span class="font-semibold text-zinc-200">{{ s.tag }}</span>
              <button
                @click="playSingleScene(i)" :disabled="running"
                class="text-xs px-2 py-0.5 rounded bg-zinc-700 hover:bg-zinc-600 disabled:opacity-40"
              >▶</button>
            </div>
            <p class="text-xs text-zinc-400 mt-1">{{ s.description }}</p>
          </li>
        </ul>

        <h2 class="text-sm uppercase tracking-wide text-zinc-400 mt-6 mb-2">
          role legend
        </h2>
        <ul class="text-xs space-y-1">
          <li><span class="inline-block w-3 h-3 mr-2 bg-role-user align-middle" />USER</li>
          <li><span class="inline-block w-3 h-3 mr-2 bg-role-llm align-middle" />LLM call</li>
          <li><span class="inline-block w-3 h-3 mr-2 bg-role-dcp_ok align-middle" />DCP ok</li>
          <li><span class="inline-block w-3 h-3 mr-2 bg-role-dcp_err align-middle" />DCP denied/error</li>
          <li><span class="inline-block w-3 h-3 mr-2 bg-role-dcp_req align-middle" />DCP in-flight</li>
        </ul>
      </aside>
    </main>
  </div>
</template>
