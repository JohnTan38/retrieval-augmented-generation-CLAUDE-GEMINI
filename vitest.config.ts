import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vitest/config'

const rootDir = path.dirname(fileURLToPath(import.meta.url))

export default defineConfig({
  esbuild: {
    jsx: 'automatic',
  },
  resolve: {
    alias: {
      '@': rootDir,
      'server-only': path.join(rootDir, 'node_modules/next/dist/compiled/server-only/empty.js'),
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./vitest.setup.ts'],
    coverage: {
      provider: 'v8',
      all: true,
      reporter: ['text', 'html'],
      exclude: [
        'app/layout.tsx',
        'app/page.tsx',
        '**/*.config.*',
        '**/*.d.ts',
        '**/*.css',
        'lib/api/types.ts',
        '.next/**',
        'dist/**',
        'tests/**',
      ],
      thresholds: {
        statements: 100,
        branches: 100,
        functions: 100,
        lines: 100,
      },
    },
  },
})
