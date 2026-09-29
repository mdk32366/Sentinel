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
    // F-0071: the suite runs in a FIXED timezone west of UTC.
    //
    // The date bug it protects against — a bare "2026-08-01" parsed as UTC
    // midnight and rendered a day earlier in local time — does not exist at
    // UTC. CI runners default to UTC, so with the ambient zone the guard
    // would have been green on the machine that matters while the defect sat
    // in production. format.test.js asserts this is in force rather than
    // trusting it.
    env: { TZ: 'America/New_York' },
  },
})
