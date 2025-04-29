import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

//  ⬇ single, unified block
export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      '/telemetry': 'http://incubator.local',
      '/setpoints': 'http://incubator.local',
      '/stream': {
        target: 'ws://incubator.local',
        ws: true,
      },
    },
  },
})
