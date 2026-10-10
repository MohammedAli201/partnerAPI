import { defineConfig, transformWithEsbuild } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath, URL } from 'node:url';

export default defineConfig({
  plugins: [{
    name: 'supplied-jsx-in-js', enforce: 'pre',
    async transform(code, id) {
      if (/\/src\/.*\.js$/.test(id.replaceAll('\\', '/'))) {
        return transformWithEsbuild(code, id, { loader: 'jsx', jsx: 'automatic' });
      }
    },
  }, react()],
  base: '/static/hubaal-react/',
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  optimizeDeps: { esbuildOptions: { loader: { '.js': 'jsx' } } },
  build: { outDir: '../static/hubaal-react', emptyOutDir: true, manifest: true },
  server: { proxy: {
    '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true,
      configure(proxy) {
        // The local dev server is the same-origin browser endpoint. Preserve the
        // backend's production Origin checks; adapt this local proxy only.
        proxy.on('proxyReq', request => { if (request.getHeader('Origin')) request.setHeader('Origin', 'http://127.0.0.1:8000'); });
      },
    },
    '/static/hubaal/': 'http://127.0.0.1:8000',
  } },
});
