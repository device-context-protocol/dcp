<script setup>
// Grid.vue — visual demo surface: a 6×6 grid with a movable square.
// Used to show DCP's range-guard mechanism viscerally: when an LLM tries
// to move out of bounds, the grid flashes red and the square doesn't move.
//
// The audience needs zero protocol knowledge — they just see "square went
// here, square didn't go there".

import { computed } from 'vue';

const props = defineProps({
  cols: { type: Number, default: 6 },
  rows: { type: Number, default: 6 },
  pos:  { type: Object, default: () => ({ x: 0, y: 0 }) },         // current cell
  ghost: { type: Object, default: () => null },                     // {x,y} attempted-but-blocked
  cellSize: { type: Number, default: 48 },
  flash: { type: String, default: '' },                             // '' | 'ok' | 'err'
});

const widthPx  = computed(() => props.cols * props.cellSize);
const heightPx = computed(() => props.rows * props.cellSize);

const cells = computed(() => {
  const arr = [];
  for (let y = 0; y < props.rows; y++) {
    for (let x = 0; x < props.cols; x++) arr.push({ x, y });
  }
  return arr;
});
</script>

<template>
  <div
    class="relative rounded-md ring-1 transition-colors duration-200"
    :class="{
      'ring-zinc-300': flash === '',
      'ring-emerald-500': flash === 'ok',
      'ring-red-500 bg-red-100': flash === 'err',
    }"
    :style="{ width: widthPx + 'px', height: heightPx + 'px' }"
  >
    <!-- grid cells -->
    <div
      v-for="c in cells" :key="`c-${c.x}-${c.y}`"
      class="absolute border border-zinc-200"
      :style="{
        left:  c.x * cellSize + 'px',
        top:   c.y * cellSize + 'px',
        width: cellSize + 'px',
        height: cellSize + 'px',
      }"
    />

    <!-- ghost target (where the LLM tried to go but was denied) -->
    <div
      v-if="ghost"
      class="absolute rounded-sm border-2 border-dashed border-red-500"
      :style="{
        left:   (ghost.x * cellSize + 4) + 'px',
        top:    (ghost.y * cellSize + 4) + 'px',
        width:  (cellSize - 8) + 'px',
        height: (cellSize - 8) + 'px',
      }"
    >
      <div class="absolute inset-0 flex items-center justify-center text-red-600 text-xl font-bold">
        ✗
      </div>
    </div>

    <!-- the actual square — animated transform -->
    <div
      class="absolute rounded-md bg-emerald-500 shadow-md ring-2 ring-emerald-700 transition-all duration-300 ease-out"
      :style="{
        left:   (pos.x * cellSize + 4) + 'px',
        top:    (pos.y * cellSize + 4) + 'px',
        width:  (cellSize - 8) + 'px',
        height: (cellSize - 8) + 'px',
      }"
    />
  </div>
</template>
