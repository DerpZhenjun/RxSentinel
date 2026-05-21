import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'node:path'

/**
 * Vite / Vitest 共用：`alias` 锁死本包 `node_modules`，避免从仓库根误解析到其他 Vue/Pinia 副本。
 * `server.fs.allow` 上浮到上级目录：开发态可读管线落到 `public` 的 JSONL。
 * `base`：GitHub Pages 项目站为 `/RxSentinel/`（由 CI 注入 PAGES_BASE）；本地 dev 默认 `/`。
 */
export default defineConfig({
  base: process.env.PAGES_BASE || '/',
  plugins: [vue()],
  resolve: {
    alias: {
      '@vue/test-utils': path.resolve(__dirname, 'node_modules/@vue/test-utils'),
      vue: path.resolve(__dirname, 'node_modules/vue'),
      pinia: path.resolve(__dirname, 'node_modules/pinia'),
    },
  },
  server: {
    fs: {
      allow: [
        path.resolve(__dirname, '..'),
      ],
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    css: false,
    include: ['../tests/frontend/**/*.test.js'],
    deps: {
      moduleDirectories: [
        'node_modules',
        path.resolve(__dirname, 'node_modules'),
      ],
    },
  },
})
