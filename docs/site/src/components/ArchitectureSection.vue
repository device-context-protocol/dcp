<template>
  <section
    id="architecture"
    class="py-20 bg-haze border-y border-border"
  >
    <div class="container-page">
      <div class="text-center max-w-[580px] mx-auto mb-11">
        <h2 class="m-0 mb-3 font-semibold tracking-[-0.02em] text-[clamp(28px,4vw,36px)]">
          How it fits together
        </h2>
        <p class="m-0 text-[17px] text-ink-soft leading-[1.5]">
          DCP sits where MCP stops. The Bridge translates between the two.
        </p>
      </div>

      <div class="bg-white border border-border rounded-2xl p-8">
        <svg
          class="w-full h-auto max-w-[880px] mx-auto block"
          viewBox="0 0 880 280" xmlns="http://www.w3.org/2000/svg"
        >
          <defs>
            <linearGradient id="g-llm" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%"  stop-color="#dbeafe" />
              <stop offset="100%" stop-color="#bfdbfe" />
            </linearGradient>
            <linearGradient id="g-device" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%"   stop-color="#fde68a" />
              <stop offset="100%" stop-color="#fcd34d" />
            </linearGradient>
            <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5"
                    markerWidth="6" markerHeight="6" orient="auto">
              <path d="M0,0 L10,5 L0,10 z" fill="#475569"/>
            </marker>
          </defs>

          <!-- LLM -->
          <rect x="40" y="100" width="140" height="80" rx="10"
                fill="url(#g-llm)" stroke="#93c5fd"/>
          <text x="110" y="135" text-anchor="middle"
                font-family="Inter,sans-serif" font-size="15" font-weight="600" fill="#0f172a">
            LLM
          </text>
          <text x="110" y="158" text-anchor="middle"
                font-family="Inter,sans-serif" font-size="11" fill="#475569">
            MCP host
          </text>

          <!-- Bridge outer -->
          <rect x="240" y="40" width="400" height="200" rx="14"
                fill="white" stroke="#1f4e79" stroke-width="1.5"/>
          <text x="440" y="65" text-anchor="middle"
                font-family="Inter,sans-serif" font-size="12" font-weight="600"
                fill="#1f4e79" letter-spacing="0.05em">
            BRIDGE — SOLE TRUST BOUNDARY
          </text>

          <!-- Bridge inner -->
          <g font-family="Inter,sans-serif" font-size="11.5" fill="#0f172a">
            <rect x="262" y="86" width="170" height="64" rx="6"
                  fill="#eef3f8" stroke="#1f4e79" stroke-opacity="0.3"/>
            <text x="347" y="113" text-anchor="middle" font-weight="600">Capability token</text>
            <text x="347" y="131" text-anchor="middle" fill="#475569" font-size="10.5">HMAC-SHA256 verify</text>

            <rect x="448" y="86" width="170" height="64" rx="6"
                  fill="#eef3f8" stroke="#1f4e79" stroke-opacity="0.3"/>
            <text x="533" y="113" text-anchor="middle" font-weight="600">Range / type</text>
            <text x="533" y="131" text-anchor="middle" fill="#475569" font-size="10.5">manifest-driven</text>

            <rect x="262" y="160" width="170" height="64" rx="6"
                  fill="#eef3f8" stroke="#1f4e79" stroke-opacity="0.3"/>
            <text x="347" y="187" text-anchor="middle" font-weight="600">Dry-run</text>
            <text x="347" y="205" text-anchor="middle" fill="#475569" font-size="10.5">wire-format kind</text>

            <rect x="448" y="160" width="170" height="64" rx="6"
                  fill="#eef3f8" stroke="#1f4e79" stroke-opacity="0.3"/>
            <text x="533" y="187" text-anchor="middle" font-weight="600">Audit / rate</text>
            <text x="533" y="205" text-anchor="middle" fill="#475569" font-size="10.5">deployment policy</text>
          </g>

          <!-- Device -->
          <rect x="700" y="100" width="140" height="80" rx="10"
                fill="url(#g-device)" stroke="#f59e0b"/>
          <text x="770" y="135" text-anchor="middle"
                font-family="Inter,sans-serif" font-size="15" font-weight="600" fill="#0f172a">
            Device
          </text>
          <text x="770" y="158" text-anchor="middle"
                font-family="Inter,sans-serif" font-size="11" fill="#475569">
            &lt; 16 KB MCU
          </text>

          <!-- Arrows -->
          <g stroke="#475569" stroke-width="1.5" fill="none">
            <line x1="182" y1="130" x2="234" y2="130" marker-end="url(#arrow)"/>
            <line x1="234" y1="150" x2="182" y2="150" marker-end="url(#arrow)"/>
            <line x1="644" y1="130" x2="696" y2="130" marker-end="url(#arrow)"/>
            <line x1="696" y1="150" x2="644" y2="150" marker-end="url(#arrow)"/>
          </g>
          <text x="208" y="124" text-anchor="middle"
                font-family="Inter,sans-serif" font-size="11" fill="#475569" font-style="italic">
            MCP
          </text>
          <text x="208" y="167" text-anchor="middle"
                font-family="Inter,sans-serif" font-size="10.5" fill="#94a3b8" font-style="italic">
            results
          </text>
          <text x="670" y="124" text-anchor="middle"
                font-family="Inter,sans-serif" font-size="11" fill="#475569" font-style="italic">
            DCP wire
          </text>
          <text x="670" y="167" text-anchor="middle"
                font-family="Inter,sans-serif" font-size="10.5" fill="#94a3b8" font-style="italic">
            reply
          </text>

          <text x="770" y="208" text-anchor="middle"
                font-family="Inter,sans-serif" font-size="10" fill="#64748b">
            UART  ·  MQTT  ·  BLE  ·  USB-CDC
          </text>
          <text x="770" y="225" text-anchor="middle"
                font-family="Inter,sans-serif" font-size="9.5" fill="#94a3b8" font-style="italic">
            one frame, any transport
          </text>
        </svg>

        <p class="text-center text-muted text-[13.5px] mt-3.5">
          The Bridge holds the manifest, issues tokens, and enforces every
          safety check before a byte traverses the device boundary.
        </p>
      </div>
    </div>
  </section>
</template>
