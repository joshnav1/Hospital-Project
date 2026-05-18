import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/triage':   'http://localhost:8000',
      '/report':   'http://localhost:8000',
      '/escalate': 'http://localhost:8000',
      '/health':   'http://localhost:8000',
    },
  },
})