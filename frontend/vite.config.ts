/// <reference types="vitest/config" />
import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  // Read VITE_API_URL etc. from the repo-root .env, per CLAUDE.md's single
  // root .env convention, rather than Vite's default of frontend/.env.
  envDir: path.resolve(import.meta.dirname, '..'),
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/setupTests.ts'],
  },
})
