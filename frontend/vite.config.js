import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/auth': 'http://localhost:8000',
      '/analyze': 'http://localhost:8000',
      '/admin': 'http://localhost:8000',
      '/upload': 'http://localhost:8000',
      // Public CMS content for the live (non-admin) pages.
      '/content': 'http://localhost:8000',
      // Proxy all billing API calls to the backend EXCEPT /billing/result,
      // which is a frontend SPA route (the post-payment result page).
      '^/billing(?!/result)': 'http://localhost:8000',
    },
  },
});
