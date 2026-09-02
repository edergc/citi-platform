import { test, expect, type Page } from '@playwright/test'

// Overridable so this can point at a CI-seeded user later without touching the test
// itself — defaults to the same técnico/admin test credentials used throughout manual
// verification this session.
const DNI = process.env.E2E_DNI ?? '12345678'
const PASSWORD = process.env.E2E_PASSWORD ?? '123456'

async function login(page: Page) {
  await page.goto('/login')
  await page.getByLabel('DNI').fill(DNI)
  await page.getByLabel('Contraseña').fill(PASSWORD)
  await page.getByRole('button', { name: 'Ingresar' }).click()
  await expect(page).toHaveURL('/')

  // The critical-alerts modal auto-pops once per browser session if there are any
  // unacknowledged critical alerts (see CriticalAlertModal.tsx) — dismiss it if present
  // so it doesn't block the rest of the page from being interacted with.
  const cerrar = page.getByRole('button', { name: 'Cerrar' })
  if (await cerrar.isVisible({ timeout: 3000 }).catch(() => false)) {
    await cerrar.click()
  }
}

test('login with valid credentials reaches the dashboard', async ({ page }) => {
  await login(page)
  await expect(page.getByRole('heading', { name: 'Centro de Aplicaciones' })).toBeVisible()
})

test('login with wrong password shows an error and stays on the login page', async ({ page }) => {
  await page.goto('/login')
  await page.getByLabel('DNI').fill(DNI)
  await page.getByLabel('Contraseña').fill('definitely-wrong-password')
  await page.getByRole('button', { name: 'Ingresar' }).click()

  await expect(page).toHaveURL(/\/login/)
  await expect(page.getByText(/incorrect/i)).toBeVisible()
})

// One entry per main sidebar destination (see Layout.tsx's navItems) — confirms each page
// renders its own heading and doesn't throw a console error, without asserting on the
// full content of any of them (that's what the Checkmk-style redesign work verified by
// hand this session; this just catches "the page is now completely broken").
const pages: { path: string; heading: string }[] = [
  { path: '/', heading: 'Centro de Aplicaciones' },
  { path: '/servers', heading: 'Gestión de Infraestructura' },
  { path: '/connectivity', heading: 'Conectividad de la flota' },
  { path: '/network', heading: 'Diagnóstico de red' },
  { path: '/problemas', heading: 'Problemas' },
  { path: '/alerts', heading: 'Alertas' },
  { path: '/mantenimiento', heading: 'Mantenimiento' },
  { path: '/sinteticos', heading: 'Chequeos sintéticos' },
  { path: '/notifications', heading: 'Notificaciones' },
  { path: '/admin', heading: 'Administración' },
]

for (const { path, heading } of pages) {
  test(`${path} renders without console errors`, async ({ page }) => {
    const errors: string[] = []
    page.on('console', (msg) => {
      if (msg.type() === 'error') errors.push(msg.text())
    })
    page.on('pageerror', (err) => errors.push(err.message))

    await login(page)
    await page.goto(path)
    await expect(page.getByText(heading).first()).toBeVisible()

    expect(errors, `console errors on ${path}: ${errors.join('\n')}`).toEqual([])
  })
}
