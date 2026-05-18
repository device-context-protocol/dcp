<script setup>
const columns = [
  'DCP',
  'MCP (direct on MCU)',
  'IoT-MCP',
  'W3C WoT',
  'Matter',
]

const rows = [
  ['Target footprint',            ['bold', '<16 KB'], '~120 KB', '74 KB', 'n/a (description)', '~256 KB'],
  ['Wire-level safety primitives', 'yes', 'no', 'no', 'no', 'partial'],
  ['Capability scoping for LLMs',  'yes', 'no', 'no', 'no', 'no'],
  ['Dry-run as wire primitive',    'yes', 'no', 'no', 'no', 'no'],
  ['Units in the schema',          'yes', 'no', 'no', 'partial', 'partial'],
  ['Transport-agnostic',           'yes', 'no', 'no', 'yes', 'no'],
  ['Custom (non-cluster) devices', 'yes', 'yes', 'yes', 'yes', 'painful'],
]

function cellClass(v) {
  if (v === 'yes')     return 'text-good font-semibold'
  if (v === 'no')      return 'text-bad font-semibold'
  if (v === 'partial' || v === 'painful') return 'text-muted'
  return ''
}
function cellLabel(v) {
  return typeof v === 'string' ? v : v[1]
}
function cellBold(v) {
  return Array.isArray(v) && v[0] === 'bold'
}
</script>

<template>
  <section id="compare" class="py-20 bg-haze border-y border-border">
    <div class="container-page">
      <div class="text-center max-w-[580px] mx-auto mb-11">
        <h2 class="m-0 mb-3 font-semibold tracking-[-0.02em] text-[clamp(28px,4vw,36px)]">
          How DCP relates to other protocols
        </h2>
        <p class="m-0 text-[17px] text-ink-soft leading-[1.5]">
          We are deliberately complementary, not competing, with most of the stack.
        </p>
      </div>

      <div class="overflow-x-auto">
        <table class="w-full border-collapse bg-white border border-border rounded-[10px] overflow-hidden text-[14px]">
          <thead>
            <tr>
              <th class="px-4 py-3.5 text-left bg-haze font-semibold text-[13px] text-ink-soft border-b border-border">
                Capability
              </th>
              <th
                v-for="c in columns" :key="c"
                class="px-4 py-3.5 text-left bg-haze font-semibold text-[13px] text-ink-soft border-b border-border"
              >{{ c }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, i) in rows" :key="i" :class="i === rows.length - 1 ? '' : 'border-b border-border'">
              <td class="px-4 py-3.5 font-medium">{{ row[0] }}</td>
              <td
                v-for="(v, j) in row.slice(1)" :key="j"
                class="px-4 py-3.5"
                :class="[cellClass(v), cellBold(v) ? 'font-bold' : '']"
              >{{ cellLabel(v) }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <p class="text-center text-ink-soft text-[13.5px] mt-4">
        DCP <a href="#spec" class="text-brand hover:text-brand-dark">imports WoT Thing Descriptions</a>.
        The reference Bridge speaks MCP natively, so any MCP host works zero-config.
      </p>
    </div>
  </section>
</template>
