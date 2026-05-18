<script setup>
const resources = [
  {
    title: 'Wire format spec',
    body:  'Six-byte header, CBOR payload, optional truncated HMAC-SHA256. Full byte-level layout, transport bindings, and golden-frame conformance tests.',
    link:  { label: 'Read the spec', href: 'https://github.com/device-context-protocol/dcp/blob/main/README.md' },
  },
  {
    title: 'Reference implementation',
    body:  'Python Bridge (asyncio, 5 transports), Arduino-compatible ESP32 firmware (<16 KB target, self-contained crypto), generic simulator, MCP server wrapper.',
    link:  { label: 'Browse the repo', href: 'https://github.com/device-context-protocol/dcp' },
  },
  {
    title: 'Design rationale',
    body:  'Why DCP, why not MCP-on-MCU, why not WoT, why not Matter. Honest comparison with prior art, including IoT-MCP.',
    link:  { label: 'Read RATIONALE.md', href: 'https://github.com/device-context-protocol/dcp/blob/main/docs/RATIONALE.md' },
  },
]
</script>

<template>
  <section id="spec" class="py-20">
    <div class="container-page">
      <div class="text-center max-w-[580px] mx-auto mb-11">
        <h2 class="m-0 mb-3 font-semibold tracking-[-0.02em] text-[clamp(28px,4vw,36px)]">
          Specification &amp; resources
        </h2>
        <p class="m-0 text-[17px] text-ink-soft leading-[1.5]">
          Everything is open source under MIT. No CLA, no certification fees.
        </p>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-3 gap-5">
        <div v-for="r in resources" :key="r.title" class="feature-card">
          <h3 class="m-0 mb-2 text-[16.5px] font-semibold tracking-[-0.01em]">{{ r.title }}</h3>
          <p class="m-0 text-[14.5px] text-ink-soft leading-[1.55]">{{ r.body }}</p>
          <p class="mt-3.5 m-0">
            <a :href="r.link.href" class="text-brand hover:text-brand-dark text-[14px] font-medium">
              {{ r.link.label }} →
            </a>
          </p>
        </div>
      </div>
    </div>
  </section>
</template>
