<script setup>
// Panel.vue — 480×480 emulator that mirrors the LilyGo T-Panel S3 firmware
// UI 1:1. The panel has two views, both inside the same 480×480 frame:
//
//   view='briefing' — scene context card (TEST / MECHANISM / WATCH)
//                     used at the start of each scene to set up the audience
//   view='demo'     — the live event-flow layout (status bar + 8 rows)
//
// The orchestrator switches view per scene phase. Both views must fit
// inside 480×480 because everything is recorded from the device frame.

import { computed } from 'vue';
import Grid from './Grid.vue';

const props = defineProps({
  view: { type: String, default: 'demo' },        // 'demo' | 'briefing' | 'grid'
  deviceId: { type: String,  default: 'DCP smart-panel-01' },
  status:   { type: String,  default: 'ready' },
  lines: {
    type: Array,
    default: () => Array.from({ length: 8 }, () => ({ text: '', role: 'plain' })),
  },
  color: { type: Object, default: () => ({ r: 40, g: 40, b: 50 }) },
  footer: { type: String, default: 'DCP v0.3.1  |  12 intents  |  CBOR/UART' },
  briefing: {
    type: Object,
    default: () => ({ testing: '', mechanism: '', watch: '', expected: '' }),
  },
  // grid-view state
  grid: {
    type: Object,
    default: () => ({ cols: 6, rows: 6, pos: { x: 0, y: 0 }, ghost: null, flash: '' }),
  },
});

const chipStyle = computed(() => ({
  backgroundColor: `rgb(${props.color.r}, ${props.color.g}, ${props.color.b})`,
}));

const roleClass = (role) => ({
  user:    'text-role-user',
  llm:     'text-role-llm',
  dcp_ok:  'text-role-dcp_ok font-medium',
  dcp_err: 'text-role-dcp_err font-medium',
  dcp_req: 'text-role-dcp_req',
  plain:   'text-role-plain',
}[role] || 'text-role-plain');
</script>

<template>
  <div
    class="relative bg-panel-bg font-panel select-none shadow-2xl ring-1 ring-black/40 overflow-hidden"
    style="width: 480px; height: 480px;"
  >
    <!-- header (device id strip — always visible) -->
    <div
      class="absolute text-[14px] leading-none text-panel-header"
      style="top: 6px; left: 10px;"
    >
      {{ deviceId }}
    </div>

    <!-- status bar — full width, no longer reserves room for a color chip -->
    <div
      class="absolute bg-panel-status text-white text-[14px] leading-none flex items-center"
      style="top: 28px; left: 10px; right: 10px; height: 30px; padding: 0 8px;"
    >
      {{ status }}
    </div>

    <!-- ──────────────────── BRIEFING VIEW ──────────────────── -->
    <template v-if="view === 'briefing'">
      <div
        class="absolute font-panel text-[14px] leading-snug text-zinc-800"
        style="top: 72px; left: 12px; right: 12px; bottom: 32px;"
      >
        <section class="mb-3">
          <div class="font-semibold text-[14px] text-amber-700 mb-0.5">
            ⚠ TEST
          </div>
          <p class="text-[13px] leading-snug">{{ briefing.testing }}</p>
        </section>

        <section class="mb-3">
          <div class="font-semibold text-[14px] text-sky-700 mb-0.5">
            🛡 MECHANISM
          </div>
          <p class="text-[13px] leading-snug">{{ briefing.mechanism }}</p>
        </section>

        <section class="mb-3">
          <div class="font-semibold text-[14px] text-emerald-700 mb-0.5">
            👁 WATCH FOR
          </div>
          <p class="text-[13px] leading-snug">{{ briefing.watch }}</p>
        </section>

        <section v-if="briefing.expected">
          <div class="font-semibold text-[14px] text-zinc-600 mb-0.5">
            ✓ EXPECTED
          </div>
          <p class="text-[13px] leading-snug">{{ briefing.expected }}</p>
        </section>
      </div>
    </template>

    <!-- ──────────────────── GRID VIEW ──────────────────── -->
    <template v-else-if="view === 'grid'">
      <!-- 3 narration rows at top: USER / LLM call / DCP response -->
      <template v-for="i in 3" :key="`g-n-${i-1}`">
        <div
          class="absolute text-[14px] leading-none truncate"
          :class="roleClass(lines[i-1]?.role)"
          :style="{ top: `${72 + (i-1)*28}px`, left: '10px', right: '10px' }"
        >
          {{ lines[i-1]?.text }}
        </div>
      </template>

      <!-- the grid, centered horizontally, below the narration -->
      <div
        class="absolute"
        style="top: 168px; left: 50%; transform: translateX(-50%);"
      >
        <Grid
          :cols="grid.cols"
          :rows="grid.rows"
          :pos="grid.pos"
          :ghost="grid.ghost"
          :flash="grid.flash"
          :cell-size="40"
        />
      </div>

      <!-- position read-out beneath the grid -->
      <div
        class="absolute text-[13px] leading-none text-zinc-600 text-center"
        style="bottom: 32px; left: 0; right: 0;"
      >
        position ({{ grid.pos.x }}, {{ grid.pos.y }})
        ·  grid {{ grid.cols }}×{{ grid.rows }}
      </div>
    </template>

    <!-- ──────────────────── DEMO VIEW ──────────────────── -->
    <template v-else>
      <!-- narration rows 0-3 -->
      <template v-for="i in 4" :key="`n-${i-1}`">
        <div
          class="absolute text-[14px] leading-none truncate"
          :class="roleClass(lines[i-1]?.role)"
          :style="{ top: `${80 + (i-1)*36}px`, left: '10px', right: '10px' }"
        >
          {{ lines[i-1]?.text }}
        </div>
      </template>

      <!-- separator -->
      <div
        class="absolute bg-panel-sep"
        style="top: 240px; left: 20px; right: 20px; height: 2px;"
      />

      <!-- LLM content rows 4-7 -->
      <template v-for="i in 4" :key="`l-${i+3}`">
        <div
          class="absolute text-[14px] leading-none truncate"
          :class="roleClass(lines[i+3]?.role)"
          :style="{ top: `${256 + (i-1)*36}px`, left: '10px', right: '10px' }"
        >
          {{ lines[i+3]?.text }}
        </div>
      </template>
    </template>

    <!-- footer — always visible -->
    <div
      class="absolute text-[14px] leading-none text-panel-footer"
      style="bottom: 8px; left: 10px; right: 10px;"
    >
      {{ footer }}
    </div>
  </div>
</template>
