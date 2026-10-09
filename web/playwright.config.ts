import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './tests', timeout: 120_000, workers: 1,
  outputDir: '../test-results/browser',
  reporter: [['list'], ['html', { outputFolder: '../test-results/browser-report', open: 'never' }]],
  use: { baseURL: 'http://127.0.0.1:8088', viewport: { width: 1440, height: 1000 }, trace: 'retain-on-failure' },
});
