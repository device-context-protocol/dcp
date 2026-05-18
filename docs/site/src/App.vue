<script setup>
import NavBar from './components/NavBar.vue'
import HeroSection from './components/HeroSection.vue'
import FeaturesSection from './components/FeaturesSection.vue'
import ArchitectureSection from './components/ArchitectureSection.vue'
import QuickstartSection from './components/QuickstartSection.vue'
import CompareSection from './components/CompareSection.vue'
import SpecSection from './components/SpecSection.vue'
import SiteFooter from './components/SiteFooter.vue'
</script>

<template>
  <NavBar />
  <main>
    <HeroSection />
    <FeaturesSection />
    <ArchitectureSection />
    <QuickstartSection />
    <CompareSection />
    <SpecSection />
  </main>
  <SiteFooter />
</template>
