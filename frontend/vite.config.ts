import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// `npm run dev` serves the desk on http://localhost:5173 and opens it in the
// browser. If 5173 is taken, Vite moves to 5174 (the backend allows both).
export default defineConfig({
  plugins: [react()],
  server: {
    host: 'localhost',
    port: 5173,
    open: true,
  },
})
