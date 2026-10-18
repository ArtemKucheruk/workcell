// @vitest-environment node
import { expect, test, vi } from 'vitest'

async function apiProxy() {
  vi.resetModules()
  return (await import('./vite.config.js')).default.server.proxy['/api']
}

test('AC9: the dev server proxies /api to FCTL_API_URL, else :4545, keeping the browser Host', async () => {
  vi.stubEnv('FCTL_API_URL', 'http://127.0.0.1:5555')
  expect(await apiProxy()).toEqual({ target: 'http://127.0.0.1:5555', changeOrigin: false })
  vi.stubEnv('FCTL_API_URL', undefined)
  expect(await apiProxy()).toEqual({ target: 'http://127.0.0.1:4545', changeOrigin: false })
})
