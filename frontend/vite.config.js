import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  // Load env file based on `mode` in the current working directory.
  // The third parameter '' loads all variables regardless of prefix.
  const env = loadEnv(mode, process.cwd(), '');

  return {
    plugins: [react()],
    server: {
      port: 5173,
      // This is necessary for Docker/WSL2 so the port is reachable from outside
      host: true,
      proxy: {
        '/api': {
          //target: 'http://localhost:8000',
          // Use the variable from Docker or .env, 
          // falling back to the backend service name we set up
          target: 'http://backend:8000',
          changeOrigin: true,
        }
      }
    }
  }
})