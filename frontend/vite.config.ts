import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'node:path'
import fs from 'node:fs'

// Flip to true once HTTPS is coordinated with TI (real cert or GPO-distributed trusted
// root for the self-signed one). Cert/key already generated at ../certs — see
// certs/generate_cert.py to regenerate/rotate. Also update .env files back to https://
// and the CitiBackend NSSM AppParameters to add --ssl-keyfile/--ssl-certfile.
const ENABLE_HTTPS = false

const certsDir = path.resolve(__dirname, '../certs')

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    host: true,
    port: 5190,
    strictPort: true,
    https: ENABLE_HTTPS
      ? {
          key: fs.readFileSync(path.join(certsDir, 'key.pem')),
          cert: fs.readFileSync(path.join(certsDir, 'cert.pem')),
        }
      : undefined,
  },
})
