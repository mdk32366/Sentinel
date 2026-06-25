import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  build: {
    // Output directly into api/static/ so FastAPI serves the built UI
    // and `fly deploy` picks it up automatically with no manual copy step.
    outDir: '../api/static',
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      // Forward /api/* calls to the local FastAPI backend during dev.
      // This avoids CORS issues — the browser sees everything on port 5173.
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
