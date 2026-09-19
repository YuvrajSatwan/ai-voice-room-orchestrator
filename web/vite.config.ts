import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// Port 5174 so this runs alongside the old UI (5173) without a clash.
export default defineConfig({
  plugins: [react()],
  server: { port: 5174, strictPort: true, host: '127.0.0.1' },
  preview: { port: 5174, strictPort: true, host: '127.0.0.1' },
  // livekit-client alone is ~500 kB minified; one realtime app bundle is expected.
  build: { chunkSizeWarningLimit: 900 },
});
