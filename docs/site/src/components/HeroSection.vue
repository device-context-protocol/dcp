<template>
  <header
    class="py-24 lg:py-28"
    style="
      background:
        radial-gradient(ellipse at 30% 0%, rgba(31,78,121,0.08), transparent 60%),
        radial-gradient(ellipse at 70% 30%, rgba(194,84,80,0.05), transparent 50%);
    "
  >
    <div class="container-page">
      <span
        class="inline-block px-3 py-1 mb-5 text-[12.5px] font-medium text-ink-soft bg-white border border-border rounded-full"
      >
        An open standard
        <span class="dot-divider"></span>
        <b class="text-brand font-semibold">complementary to MCP</b>
      </span>

      <h1
        class="m-0 font-bold leading-[1.08] tracking-[-0.025em] text-[clamp(38px,5.5vw,56px)]"
      >
        The protocol that lets LLMs<br />
        safely control physical devices.
      </h1>

      <p
        class="mt-5 mb-8 max-w-[640px] text-ink-soft leading-[1.5] text-[clamp(17px,2vw,19px)]"
      >
        <strong class="text-ink">DCP</strong> is a compact wire format and architecture purpose-built for
        LLM-driven control of constrained hardware. Sub-50-byte frames. A target firmware
        footprint under 16&nbsp;KB. Capability scoping, dry-run, and unit-aware schema as
        protocol-layer primitives — not application discipline.
      </p>

      <div class="flex flex-wrap gap-3">
        <a href="#quickstart" class="btn btn-primary">
          Get started <span class="text-base leading-none">→</span>
        </a>
        <a href="https://github.com/device-context-protocol" class="btn btn-secondary">
          View on GitHub
        </a>
        <a
          href="https://arxiv.org/abs/2605.26159"
          class="btn btn-secondary"
          target="_blank"
          rel="noopener"
        >
          Read the paper
          <span class="ml-1 px-1.5 py-0.5 rounded text-[10.5px] font-mono font-semibold bg-[#b31b1b] text-white align-middle">
            arXiv
          </span>
        </a>
      </div>
    </div>
  </header>
</template>
