import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: parseInt(process.env.WEB_PORT || '8088'),
    proxy: {
      '/api': {
        target: `http://localhost:${process.env.API_PORT || '5006'}`,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, '')
      }
    }
  },
  preview: {
    host: '0.0.0.0',
    port: parseInt(process.env.WEB_PORT || '8088')
  }
})

