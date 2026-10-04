import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 开发时 /api 代理到本机后端；容器内由 nginx 反代 backend:8000
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
