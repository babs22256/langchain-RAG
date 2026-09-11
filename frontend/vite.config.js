import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 开发环境通过代理转发 /api 到后端，避免跨域问题
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, '')
      }
    }
  }
})
