<script setup>
const features = [
  {
    title: 'Built for <16 KB MCUs',
    body:  'A 6-byte fixed header plus CBOR. No JSON, no runtime discovery, no WebSocket. Targets the Cortex-M0+ class of microcontroller that MCP and Matter cannot reach.',
    icon:  'm3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z',
  },
  {
    title: 'Safety at the protocol layer',
    body:  'A Bridge process is the sole trust boundary. Capability tokens, range and type checks, dry-run as a wire-format bit — all enforced before any byte reaches the device. LLMs never see raw GPIO.',
    icon:  'M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z',
  },
  {
    title: 'One wire, every transport',
    body:  'The same frame format runs over UART, BLE GATT, MQTT, and USB CDC. Move from breadboard prototype to shipped product without changing the protocol — only the transport class.',
    icon:  'M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z',
  },
]
</script>

<template>
  <section id="overview" class="py-20">
    <div class="container-page">
      <div class="text-center max-w-[580px] mx-auto mb-11">
        <h2 class="m-0 mb-3 font-semibold tracking-[-0.02em] text-[clamp(28px,4vw,36px)]">
          Why DCP
        </h2>
        <p class="m-0 text-[17px] text-ink-soft leading-[1.5]">
          Three structural advantages others can't trivially copy.
        </p>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-3 gap-5">
        <div
          v-for="f in features" :key="f.title"
          class="feature-card"
        >
          <div
            class="w-[38px] h-[38px] rounded-lg grid place-items-center text-white mb-[18px]"
            style="background: linear-gradient(135deg, var(--color-brand), var(--color-brand-light))"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none"
                 stroke="currentColor" stroke-width="2"
                 stroke-linecap="round" stroke-linejoin="round">
              <path :d="f.icon" />
            </svg>
          </div>
          <h3 class="m-0 mb-2 text-[16.5px] font-semibold tracking-[-0.01em]">{{ f.title }}</h3>
          <p class="m-0 text-[14.5px] text-ink-soft leading-[1.55]">{{ f.body }}</p>
        </div>
      </div>
    </div>
  </section>
</template>
