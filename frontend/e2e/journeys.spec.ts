import { expect, test, type Page } from '@playwright/test'
import { fileURLToPath } from 'node:url'

const password = process.env.E2E_PASSWORD
if (!password) throw new Error('Defina E2E_PASSWORD com a mesma senha usada em E2E_SEED_PASSWORD')

const email = (role: string) => `e2e-${role}@ilya-test.invalid`
const photo = fileURLToPath(new URL('../../backend/tests/fixtures/images/valid-small.png', import.meta.url))

async function login(page: Page, role = 'admin', market: 'BR' | 'EU' = 'BR') {
  await page.goto('/login')
  await page.getByLabel('E-mail ou Usuário').fill(email(role))
  await page.getByLabel('Senha').fill(password!)
  await page.getByRole('button', { name: 'Entrar' }).click()
  if (role === 'admin') {
    await page.getByRole('heading', { name: 'Escolha o ambiente' }).waitFor()
    await page.getByRole('button', { name: market === 'BR' ? 'Brasil' : 'Portugal' }).click()
  }
  await expect(page).toHaveURL(/\/(cadastros|orcamentos|dashboard)(?:\?.*)?$/)
}

async function switchMarket(page: Page, from: 'BR' | 'EU', to: 'BR' | 'EU') {
  await page.getByRole('button', { name: `Ambiente ${from === 'BR' ? 'Brasil' : 'Portugal'}. Trocar ambiente` }).click()
  await page.getByRole('menuitemradio', { name: to === 'BR' ? 'Brasil' : 'Portugal' }).click()
  await expect(page.getByRole('button', { name: `Ambiente ${to === 'BR' ? 'Brasil' : 'Portugal'}. Trocar ambiente` })).toBeVisible()
}

async function addProduct(page: Page, code: 'BR' | 'EU') {
  await page.goto('/produtos')
  const description = `Produto E2E ${code}`
  await page.getByRole('textbox', { name: 'Pesquisar produtos' }).fill(`E2E-${code}-001`)
  await page.getByRole('button', { name: `Adicionar ${description} ao orçamento` }).click()
  await page.goto('/orcamentos')
  await expect(page.getByRole('region', { name: 'Itens do Orçamento' })).toContainText(`E2E-${code}-001`)
}

async function createOrder(page: Page, code: 'BR' | 'EU') {
  await addProduct(page, code)
  const client = page.getByPlaceholder('Buscar cliente...').last()
  await client.fill(`Cliente E2E ${code}`)
  await page.getByRole('option', { name: new RegExp(`Cliente E2E ${code}`) }).click()
  const responsePromise = page.waitForResponse(response => response.url().includes('/api/v1/orders') && response.request().method() === 'POST')
  await page.getByRole('button', { name: 'Finalizar Orçamento' }).click()
  const response = await responsePromise
  expect(response.ok()).toBeTruthy()
  const created = await response.json() as { code: string }
  await expect(page.getByText('Orçamento finalizado com sucesso!')).toBeVisible()
  await page.goto('/pedidos')
  await expect(page.getByRole('row').filter({ hasText: created.code })).toBeVisible()
}

test('E2E-01: login e troca de mercado BR/EU', async ({ page }) => {
  await login(page)
  await expect(page.getByRole('button', { name: 'Ambiente Brasil. Trocar ambiente' })).toBeVisible()
  await switchMarket(page, 'BR', 'EU')
  await switchMarket(page, 'EU', 'BR')
})

test('E2E-02: catálogo e fotos ficam no mercado correto', async ({ page }) => {
  await login(page)
  for (const code of ['BR', 'EU'] as const) {
    if (code === 'EU') await switchMarket(page, 'BR', 'EU')
    await page.goto('/cadastros')
    await page.getByRole('textbox', { name: 'Buscar produtos por código ou descrição' }).fill(`E2E-${code}-001`)
    const row = page.getByRole('row').filter({ hasText: `E2E-${code}-001` })
    await expect(row).toBeVisible()
    await row.getByRole('button', { name: 'Editar' }).click()
    await expect(page.getByRole('heading', { name: 'Editar Produto' })).toBeVisible()
    await page.locator('.modal-overlay input[type=file]').setInputFiles(photo)
    await page.getByRole('button', { name: 'Salvar' }).click()
    const image = row.locator('[data-product-col="photo"] img')
    await expect(image).toBeVisible()
    await expect.poll(() => image.evaluate(element => (element as HTMLImageElement).naturalWidth)).toBeGreaterThan(0)
    await expect(page.getByRole('row').filter({ hasText: `E2E-${code === 'BR' ? 'EU' : 'BR'}-001` })).toHaveCount(0)
  }
})

test('E2E-03: pedido brasileiro pela interface', async ({ page }) => {
  await login(page)
  await createOrder(page, 'BR')
})

test('E2E-04: pedido europeu pela interface', async ({ page }) => {
  await login(page, 'admin', 'EU')
  await createOrder(page, 'EU')
})

test('E2E-05: cada papel respeita as rotas permitidas', async ({ browser, baseURL }) => {
  const expectations = [
    { role: 'executivo', home: '/dashboard', denied: '/pedidos' },
    { role: 'cadastros', home: '/cadastros', denied: '/orcamentos' },
    { role: 'produtos', home: '/cadastros', denied: '/admin' },
    { role: 'cliente', home: '/orcamentos', denied: '/cadastros' },
  ]
  for (const { role, home, denied } of expectations) {
    const context = await browser.newContext({ baseURL })
    try {
      const page = await context.newPage()
      await login(page, role)
      await expect(page).toHaveURL(new RegExp(`${home}$`))
      await page.goto(denied)
      await expect(page).toHaveURL(new RegExp(`${home}$`))
    } finally {
      await context.close()
    }
  }
})

test('E2E-06: carrinho e resposta antiga não atravessam a troca de mercado', async ({ page }) => {
  await login(page)
  await addProduct(page, 'BR')
  await switchMarket(page, 'BR', 'EU')
  await page.goto('/orcamentos')
  await expect(page.getByRole('region', { name: 'Itens do Orçamento' })).not.toContainText('E2E-BR-001')
  await addProduct(page, 'EU')
  await switchMarket(page, 'EU', 'BR')
  await page.goto('/orcamentos')
  await expect(page.getByRole('region', { name: 'Itens do Orçamento' })).toContainText('E2E-BR-001')
  await expect(page.getByRole('region', { name: 'Itens do Orçamento' })).not.toContainText('E2E-EU-001')

  // Hold an already received BR catalog response while identity rotates.
  let release!: () => void
  let intercepted!: () => void
  const held = new Promise<void>(resolve => { release = resolve })
  const seen = new Promise<void>(resolve => { intercepted = resolve })
  let first = true
  await page.route(/\/api\/v1\/products(?:\?|$)/, async route => {
    if (!first) return route.continue()
    first = false
    const response = await route.fetch()
    intercepted()
    await held
    try { await route.fulfill({ response }) } catch { /* aborted when session rotates */ }
  })
  await page.goto('/produtos')
  await seen
  await switchMarket(page, 'BR', 'EU')
  release()
  await page.getByRole('textbox', { name: 'Pesquisar produtos' }).fill('E2E-EU-001')
  await expect(page.getByRole('button', { name: 'Adicionar Produto E2E EU ao orçamento' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Adicionar Produto E2E BR ao orçamento' })).toHaveCount(0)
})
