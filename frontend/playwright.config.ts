import { defineConfig, devices } from '@playwright/test'
import { mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'

const runtimeRoot = mkdtempSync(join(tmpdir(), 'xhs-workbench-e2e-'))
const databasePath = join(runtimeRoot, 'workbench.sqlite').replaceAll('\\', '/')
const repositoryRoot = resolve(import.meta.dirname, '..')
const apiToken = 'e2e-api-token'
const sharedEnvironment = {
  ...process.env,
  DATABASE_URL: `sqlite:///${databasePath}`,
  EXPORT_DIR: join(runtimeRoot, 'exports'),
  UPLOAD_ROOT: join(runtimeRoot, 'uploads'),
  E2E_RUNTIME_ROOT: runtimeRoot,
  LLM_PROVIDER: 'mock',
  IMAGE_PROVIDER: 'mock',
  WORKER_ENABLED: 'true',
  API_TOKEN: apiToken,
}

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? 'github' : 'list',
  use: {
    baseURL: 'http://127.0.0.1:5174',
    trace: 'retain-on-failure',
    ...devices['Desktop Chrome'],
  },
  webServer: [
    {
      command: 'uv run python scripts/start_e2e_backend.py',
      cwd: repositoryRoot,
      env: sharedEnvironment,
      url: 'http://127.0.0.1:8090/healthz',
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      command: 'npm run dev -- --host 127.0.0.1 --port 5174 --strictPort',
      cwd: import.meta.dirname,
      env: {
        ...process.env,
        VITE_API_BASE: 'http://127.0.0.1:8090',
        VITE_API_TOKEN: apiToken,
      },
      url: 'http://127.0.0.1:5174',
      reuseExistingServer: false,
      timeout: 60_000,
    },
  ],
})
