import { fileURLToPath, URL } from 'node:url'

import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // Where the FastAPI backend runs: VITE_API_URL in .env
  const backend = loadEnv(mode, process.cwd()).VITE_API_URL || 'http://127.0.0.1:8000'

  return {
    plugins: [react(), tailwindcss()],
    resolve: {
      // Lets any file write `@/components/...` instead of `../../components/...`
      alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
    },
    server: {
      port: 5173, // the address the backend's CORS setting (FRONTEND_ORIGIN) expects
      strictPort: true,
      // The dashboard calls `/api/leads`; Vite quietly forwards it to the
      // backend's `/leads`. So the browser sees one single site (no CORS
      // trouble, live feed included).
      proxy: {
        '/api': {
          target: backend,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api/, ''),
        },
      },
    },
  }
})
