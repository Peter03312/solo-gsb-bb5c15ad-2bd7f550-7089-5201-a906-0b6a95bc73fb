import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 开发环境把 /api 代理到后端；生产环境由 nginx 代理（见 nginx.conf）
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
