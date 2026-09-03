import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Allow ngrok (and similar) Host headers in Vite 8+.
    allowedHosts: true,
    // Same-origin proxy so a single ngrok URL works (no browser CORS,
    // no ngrok interstitial on API fetch).
    proxy: {
      '/api': 'http://127.0.0.1:8000',
      '/health': 'http://127.0.0.1:8000',
    },
  },
})
