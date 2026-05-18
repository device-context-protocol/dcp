<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'

const scrolled = ref(false)
const onScroll = () => {
  scrolled.value = window.scrollY > 8
}

onMounted(() => window.addEventListener('scroll', onScroll, { passive: true }))
onBeforeUnmount(() => window.removeEventListener('scroll', onScroll))

const links = [
  { href: '#overview',   label: 'Overview'   },
  { href: '#quickstart', label: 'Quickstart' },
  { href: '#spec',       label: 'Spec'       },
  { href: '#compare',    label: 'Compare'    },
]
</script>

<template>
  <nav
    class="sticky top-0 z-50 border-b border-border bg-white/85 backdrop-blur-md transition-shadow"
    :class="scrolled ? 'shadow-sm' : ''"
  >
    <div class="container-page h-14 flex items-center justify-between">
      <a href="#" class="flex items-center gap-2.5 font-semibold text-[15px] text-ink">
        <span
          class="grid place-items-center w-[26px] h-[26px] rounded-md text-white text-[13px] font-bold"
          style="background: linear-gradient(135deg, var(--color-brand), var(--color-brand-light))"
        >D</span>
        <span>DCP</span>
      </a>

      <div class="flex items-center gap-7">
        <a
          v-for="l in links" :key="l.href"
          :href="l.href"
          class="hidden md:inline text-sm font-medium text-ink-soft hover:text-ink transition-colors"
        >{{ l.label }}</a>
        <a
          href="https://github.com/device-context-protocol"
          class="px-3.5 py-1.5 bg-ink text-white rounded-[7px] text-[13.5px] font-medium hover:bg-brand transition-colors"
        >GitHub →</a>
      </div>
    </div>
  </nav>
</template>
