<template>
  <div class="flex flex-col items-center">
    <svg width="110" height="60" viewBox="0 0 110 60">
      <path
        d="M10 55 A45 45 0 0 1 100 55"
        fill="none"
        stroke="#e2e8f0"
        stroke-width="10"
        stroke-linecap="round" />
      <path
        :d="arcPath"
        fill="none"
        stroke="#3b82f6"
        stroke-width="10"
        stroke-linecap="round" />
      <text x="55" y="35" text-anchor="middle" font-size="14" fill="#111">
        {{ value.toFixed(1) }}{{ units }}
      </text>
    </svg>
    <span class="text-sm mt-1">{{ label }}</span>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  value:   { type: Number, required: true },
  label:   { type: String, required: true },
  units:   { type: String, default: '' },
  min:     { type: Number, default: 0 },
  max:     { type: Number, default: 100 },
})

const arcPath = computed(() => {
  const pct = (props.value - props.min) / (props.max - props.min)
  const angle = 180 * pct      // 0-180°
  const r = 45, cx = 55, cy = 55
  const rad = (Math.PI * (180 - angle)) / 180
  const x = cx + r * Math.cos(rad)
  const y = cy - r * Math.sin(rad)
  return `M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${x} ${y}`
})
</script>

<style scoped>
svg { user-select: none }
</style>
