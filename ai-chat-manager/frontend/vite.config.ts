// vite.config.ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000, // Or your frontend port (e.g., 5173 if that's what you use)
    proxy: {
      '/api': {
        target: 'http://localhost:8000', // Your FastAPI backend
        changeOrigin: true,
        secure: false,
        ws: true, // <--- ADD THIS LINE
      },
    },
  },
})