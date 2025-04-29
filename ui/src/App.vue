<script setup>
import { ref, onMounted } from 'vue'
import axios from 'axios'
import Gauge from './components/Gauge.vue'

/* --- state --- */
const telemetry = ref({
  temperature: 0,
  humidity:    0,
  co2:         0,
  o2:          0,
  setpoints:   { temperature: 37, humidity: 60, co2: 5, o2: 5 }
})

/* --- REST poll once on load --- */
onMounted(fetchOnce)
async function fetchOnce () {
  const { data } = await axios.get('/telemetry')   // proxied to incubator.local
  telemetry.value = data
}

/* --- live WebSocket stream --- */
onMounted(() => {
  const ws = new WebSocket('ws://incubator.local/stream')
  ws.onmessage = ev => {
    const j = JSON.parse(ev.data)
    telemetry.value.temperature = j.temp
    telemetry.value.setpoints.temperature = j.sp
  }
})

/* --- push set-point example --- */
async function save () {
  await axios.put('/setpoints', { temperature: telemetry.value.setpoints.temperature })
}
</script>

<template>
  <main class="p-8 space-y-8 font-sans">
    <h1 class="text-2xl font-bold">Portable Incubator Dashboard</h1>

    <!-- gauges -->
    <div class="grid grid-cols-2 gap-6 max-w-lg">
      <Gauge
        :value="telemetry.temperature"
        :min="20" :max="50"
        units="°C"
        label="Temp" />

      <Gauge
        :value="telemetry.humidity"
        :min="0" :max="100"
        units="%"
        label="RH" />

      <Gauge
        :value="telemetry.co2"
        :min="0" :max="20"
        units="%"
        label="CO₂" />

      <Gauge
        :value="telemetry.o2"
        :min="0" :max="21"
        units="%"
        label="O₂" />
    </div>

    <!-- quick set-point control -->
    <div class="space-x-2">
      <label class="font-medium">Temp&nbsp;set-point&nbsp;(°C):</label>
      <input
        v-model.number="telemetry.setpoints.temperature"
        type="number"
        class="border px-2 py-1 w-20" />
      <button @click="save"
              class="bg-blue-600 hover:bg-blue-700 text-white px-4 py-1 rounded">
        Save
      </button>
    </div>
  </main>
</template>

<style>
@import "https://cdn.jsdelivr.net/npm/tailwindcss@^3/dist/tailwind.min.css";
body { background:#f8fafc; }
</style>
