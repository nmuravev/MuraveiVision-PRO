import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  base: './',
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    host: '127.0.0.1',
    port: 3000,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://127.0.0.1:8000',
        ws: true,
      },
    },
    watch: {
      ignored: [
        '**/archive/**',
        '**/runs/**',
        '**/muravei_env/**',
        '**/reports/**',
        '**/portable/**',
        '**/sidecars/**',
        '**/.backup/**',
        '**/openreel-reference/**',
      ],
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    sourcemap: false,
    rollupOptions: {
      output: {
        manualChunks(id) {
          const n = id.replace(/\\/g, '/');
          if (n.includes('gaussian-splats-3d')) {
            return 'vendor-splats';
          }
          if (n.includes('node_modules/three/examples')) {
            return 'vendor-three-examples';
          }
          if (n.includes('node_modules/three')) {
            return 'vendor-three';
          }
          if (n.includes('react-mosaic-component')) {
            return 'vendor-mosaic';
          }
          if (
            n.includes('node_modules/react/') ||
            n.includes('node_modules/react-dom') ||
            n.includes('node_modules/scheduler') ||
            n.includes('node_modules/zustand')
          ) {
            return 'vendor-react';
          }
          return undefined;
        },
      },
    },
  },
})
