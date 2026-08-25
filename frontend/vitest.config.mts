import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    exclude: ['**/node_modules/**', '**/.next/**', 'e2e/**'],
    // No component/unit tests exist yet — behavior is currently
    // verified via the Playwright e2e suite (npm run test:e2e).
    passWithNoTests: true,
  },
});
