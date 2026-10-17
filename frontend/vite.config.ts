import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import process from 'node:process'

const apiTarget = process.env.SERVICEOS_VITE_API_TARGET ?? 'http://127.0.0.1:8000'
const devPort = Number(process.env.SERVICEOS_VITE_PORT ?? 5173)
const proxy = { '/api': { target: apiTarget, changeOrigin: true } }

export default defineConfig({
  plugins: [react()],
  server: { host: '127.0.0.1', port: devPort, strictPort: true, proxy },
  preview: { host: '127.0.0.1', port: 4173, strictPort: true, proxy },
})
