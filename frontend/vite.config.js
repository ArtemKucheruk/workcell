import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // Q11: Vite's string shorthand turns changeOrigin on, so the object form keeps the browser's Host
    // and the backend's own Host check still applies in dev
    proxy: { '/api': { target: process.env.FCTL_API_URL || 'http://127.0.0.1:4545', changeOrigin: false } },
  },
  test: { environment: 'jsdom', unstubGlobals: true, unstubEnvs: true },
})
