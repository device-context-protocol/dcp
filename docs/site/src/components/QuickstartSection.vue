<script setup>
import { computed } from 'vue'

const blocks = [
  {
    label: '1. Install',
    html: `<span class="prompt">$</span> <span class="cmd">pip install dcp[mcp]</span>
<span class="prompt">$</span> <span class="cmd">dcp inspect lamp.yaml</span>
device: lamp-kitchen-01
intents:
  - set_brightness   <span class="com"># cap=lamp.write</span>
  - read_brightness  <span class="com"># cap=lamp.read</span>`,
  },
  {
    label: '2. Manifest (lamp.yaml)',
    html: `<span class="key">dcp</span>: 0.1
<span class="key">device</span>: { id: lamp-kitchen-01 }
<span class="key">intents</span>:
  - <span class="key">name</span>: set_brightness
    <span class="key">params</span>:
      level: { type: float, unit: <span class="str">percent</span>,
               range: [0, 100] }
    <span class="key">capability</span>: lamp.write
    <span class="key">dry_run</span>: true`,
  },
  {
    label: '3. Launch the Bridge',
    html: `<span class="prompt">$</span> <span class="cmd">dcp serve lamp.yaml --simulator</span>
<span class="com"># 23:01:14  dcp.mcp  ready · device=lamp-kitchen-01</span>
<span class="com"># 23:01:14  dcp.mcp  intents=2  caps=[lamp.read, lamp.write]</span>`,
  },
  {
    label: '4. Wire to Claude Desktop',
    html: `<span class="com">// claude_desktop_config.json</span>
{
  <span class="str">"mcpServers"</span>: {
    <span class="str">"lamp"</span>: {
      <span class="str">"command"</span>: <span class="str">"dcp"</span>,
      <span class="str">"args"</span>: [<span class="str">"serve"</span>, <span class="str">"lamp.yaml"</span>,
               <span class="str">"--simulator"</span>]
    }
  }
}`,
  },
]
</script>

<template>
  <section id="quickstart" class="py-20">
    <div class="container-page">
      <div class="text-center max-w-[580px] mx-auto mb-11">
        <h2 class="m-0 mb-3 font-semibold tracking-[-0.02em] text-[clamp(28px,4vw,36px)]">
          Quickstart
        </h2>
        <p class="m-0 text-[17px] text-ink-soft leading-[1.5]">
          Run an LLM-controlled simulated device in under a minute. No hardware required.
        </p>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-2 gap-5">
        <div v-for="b in blocks" :key="b.label">
          <div class="inline-block text-[11.5px] font-medium uppercase tracking-[0.08em] text-muted mb-2.5">
            {{ b.label }}
          </div>
          <pre class="code-card" v-html="b.html"></pre>
        </div>
      </div>

      <div class="text-center mt-9">
        <span class="kbd">/dim the lamp to 30%</span>
        <span class="text-ink-soft text-[14.5px] ml-2">— and the LLM does the rest.</span>
      </div>
    </div>
  </section>
</template>
