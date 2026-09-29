import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  test: {
    // Most suites here are pure functions and run fine in node. The tab render
    // tests declare `// @vitest-environment jsdom` at the top of the file, so
    // the DOM cost stays on the files that need it. environmentMatchGlobs was
    // the other way to do this and is deprecated in Vitest 5.
    environment: 'node',
    globals: false,
  },
})
