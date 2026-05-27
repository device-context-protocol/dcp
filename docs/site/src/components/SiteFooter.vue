<script setup>
const cols = [
  {
    title: 'Protocol',
    items: [
      { label: 'Specification', href: '#spec' },
      { label: 'Architecture',  href: '#architecture' },
      { label: 'Comparison',    href: '#compare' },
      { label: 'Rationale',     href: 'https://github.com/device-context-protocol/dcp/blob/main/docs/RATIONALE.md' },
      { label: 'Paper (arXiv:2605.26159)', href: 'https://arxiv.org/abs/2605.26159' },
    ],
  },
  {
    title: 'Develop',
    items: [
      { label: 'Quickstart',         href: '#quickstart' },
      { label: 'Reference impl',     href: 'https://github.com/device-context-protocol/dcp' },
      { label: 'ESP32 firmware',     href: 'https://github.com/device-context-protocol/dcp/tree/main/firmware/esp32' },
      { label: 'Conformance suite',  href: 'https://github.com/device-context-protocol/dcp/tree/main/tests/conformance' },
    ],
  },
  {
    title: 'Community',
    items: [
      { label: 'Discussions',  href: 'https://github.com/device-context-protocol/dcp/discussions' },
      { label: 'Issues',       href: 'https://github.com/device-context-protocol/dcp/issues' },
      { label: 'Contributing', href: 'https://github.com/device-context-protocol/dcp/blob/main/CONTRIBUTING.md' },
      { label: 'Security',     href: 'https://github.com/device-context-protocol/dcp/blob/main/SECURITY.md' },
    ],
  },
]
</script>

<template>
  <footer class="bg-deep text-slate-300 py-14 pb-8">
    <div class="container-page">
      <div class="grid grid-cols-2 md:grid-cols-[2fr_1fr_1fr_1fr] gap-7 mb-10">
        <div>
          <div class="flex items-center gap-2.5 text-white font-semibold mb-3">
            <span
              class="grid place-items-center w-[26px] h-[26px] rounded-md text-white text-[13px] font-bold"
              style="background: linear-gradient(135deg, #2d6ba5, #9fbedb)"
            >D</span>
            DCP
          </div>
          <p class="text-slate-400 text-[13.5px] max-w-[280px] m-0">
            An open protocol for LLM-driven control of physical devices. MIT licensed.
          </p>
        </div>

        <div v-for="c in cols" :key="c.title">
          <h4 class="m-0 mb-3.5 text-[12.5px] text-slate-400 uppercase tracking-[0.1em] font-semibold">
            {{ c.title }}
          </h4>
          <ul class="list-none p-0 m-0">
            <li v-for="it in c.items" :key="it.label" class="mb-2.5">
              <a :href="it.href" class="text-slate-300 hover:text-white text-[14px] transition-colors">
                {{ it.label }}
              </a>
            </li>
          </ul>
        </div>
      </div>

      <div class="pt-7 border-t border-slate-800 flex flex-wrap justify-between items-center gap-4 text-slate-500 text-[13px]">
        <span>© 2026 DCP authors · MIT licensed · Not affiliated with Anthropic, Inc.</span>
        <span class="font-mono text-[11px]">v0.3.1 · spec draft</span>
      </div>
    </div>
  </footer>
</template>
