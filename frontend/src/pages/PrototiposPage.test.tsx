import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { describe, expect, it, vi } from 'vitest'
import { server } from '../test/setup'
import { installProductHandlers, productFixture, productTestUser, renderProductPage } from '../test/productTestUtils'
import ProdutosPage from './ProdutosPage'
import PrototiposPage from './PrototiposPage'

const CATALOG = { id: 'cat-1', name: 'IBTW' }

function permittedUser(permitted = true) {
  return { ...productTestUser('vendedor', 'EU'), can_manage_prototypes: permitted }
}

function prototypeFixture(code = 'PROT-0001', overrides: Record<string, unknown> = {}) {
  return {
    ...productFixture('EU', {
      id: `proto-${code}`, product_code: code, description: 'Poltrona protótipo',
      catalog_id: CATALOG.id, catalog: CATALOG, altura: 0.8, largura: 0.7,
    }),
    is_prototype: true, vat_rate: '23.00', photos: [], photo_count: 0,
    ...overrides,
  }
}

function listHandler(items: ReturnType<typeof prototypeFixture>[], seen: string[] = []) {
  return http.get('*/prototypes', ({ request }) => {
    seen.push(new URL(request.url).search)
    return HttpResponse.json(items, {
      headers: { 'X-Total-Count': String(items.length), 'X-Has-More': 'false', 'X-Page-Size': String(items.length) },
    })
  })
}

describe('PrototiposPage', () => {
  it('não mostra nada nem chama a API sem a permissão', async () => {
    const calls = vi.fn()
    installProductHandlers({ catalogs: [CATALOG] })
    server.use(http.get('*/prototypes', () => { calls(); return HttpResponse.json([]) }))
    renderProductPage(<PrototiposPage />, permittedUser(false), ['/prototipos'])
    await new Promise(resolve => setTimeout(resolve, 50))
    expect(screen.queryByRole('heading', { name: 'Protótipos' })).not.toBeInTheDocument()
    expect(calls).not.toHaveBeenCalled()
  })

  it('o admin (acesso sempre) vê o aviso de que enxerga os protótipos de todos', async () => {
    installProductHandlers({ catalogs: [CATALOG] })
    server.use(listHandler([prototypeFixture('PROT-0002', { description: 'Do James' })]))
    const admin = { ...productTestUser('admin', 'EU'), can_manage_prototypes: true }
    renderProductPage(<PrototiposPage />, admin, ['/prototipos'])
    expect(await screen.findByText('PROT-0002')).toBeInTheDocument()
    expect(screen.getByText(/Como admin, você vê e usa os protótipos de todos/)).toBeInTheDocument()
    expect(screen.queryByText(/Só você vê estes itens/)).not.toBeInTheDocument()
  })

  it('lista os protótipos do usuário e busca por texto', async () => {
    const seen: string[] = []
    installProductHandlers({ catalogs: [CATALOG] })
    server.use(listHandler([prototypeFixture()], seen))
    renderProductPage(<PrototiposPage />, permittedUser(), ['/prototipos'])
    expect(await screen.findByText('PROT-0001')).toBeInTheDocument()
    expect(screen.getByText('Poltrona protótipo')).toBeInTheDocument()
    await userEvent.type(screen.getByLabelText('Buscar protótipos'), 'poltrona')
    await waitFor(() => expect(seen.some(search => search.includes('q=poltrona'))).toBe(true))
  })

  it('cria o protótipo com o código automático e o IVA informado', async () => {
    const created: Array<Record<string, unknown>> = []
    installProductHandlers({ catalogs: [CATALOG] })
    server.use(
      listHandler([]),
      http.post('*/prototypes', async ({ request }) => {
        const body = await request.json() as Record<string, unknown>
        created.push(body)
        return HttpResponse.json({ ...prototypeFixture('PROT-0007'), ...body, description: body.description_pt_pt }, { status: 201 })
      }),
      http.get('*/prototypes/:id/optional-groups', () => HttpResponse.json([])),
    )
    renderProductPage(<PrototiposPage />, permittedUser(), ['/prototipos'])
    await userEvent.click(await screen.findByRole('button', { name: /Novo protótipo/ }))
    const form = await screen.findByRole('form', { name: 'Formulário de protótipo' })
    expect(within(form).getByText('PROT-xxxx (automático)')).toBeInTheDocument()
    await userEvent.type(within(form).getByLabelText(/Nome em português/), 'Poltrona protótipo')
    await userEvent.type(within(form).getByLabelText(/Nome em inglês/), 'Prototype armchair')
    await userEvent.selectOptions(within(form).getByLabelText(/Catálogo/), CATALOG.id)
    await userEvent.type(within(form).getByLabelText(/Altura/), '0.8')
    await userEvent.type(within(form).getByLabelText(/Largura/), '0.7')
    const pvp = within(form).getByLabelText('PVP')
    await userEvent.clear(pvp)
    await userEvent.type(pvp, '1500')
    const vat = within(form).getByLabelText(/IVA/)
    await userEvent.clear(vat)
    await userEvent.type(vat, '6')
    await userEvent.click(within(form).getByRole('button', { name: 'Criar protótipo' }))

    await waitFor(() => expect(created).toHaveLength(1))
    expect(created[0]).toMatchObject({
      description_pt_pt: 'Poltrona protótipo', description_en: 'Prototype armchair',
      catalog_id: CATALOG.id, altura: 0.8, largura: 0.7, price_pvp: 1500, vat_rate: 6,
    })
    expect(created[0]).not.toHaveProperty('product_code')
    expect(await screen.findByText(/Protótipo PROT-0007 criado/)).toBeInTheDocument()
  })

  it('sobe as fotos escolhidas logo depois de criar, a primeira como principal', async () => {
    const order: string[] = []
    installProductHandlers({ catalogs: [CATALOG] })
    server.use(
      listHandler([]),
      http.post('*/prototypes', async ({ request }) => {
        order.push('create')
        const body = await request.json() as Record<string, unknown>
        return HttpResponse.json({ ...prototypeFixture('PROT-0009'), ...body, description: body.description_pt_pt }, { status: 201 })
      }),
      http.post('*/prototypes/:id/photos', async ({ params }) => {
        order.push(`photo:${String(params.id)}`)
        const photo = { id: `ph-${order.length}`, position: order.length - 2, is_primary: order.length === 2, photo_url: '/m/a.png', thumbnail_url: '/m/a-t.webp' }
        return HttpResponse.json({ ...prototypeFixture('PROT-0009'), photos: [photo], photo_count: 1, photo_url: '/m/a.png', thumbnail_url: '/m/a-t.webp' }, { status: 201 })
      }),
      http.get('*/prototypes/:id/optional-groups', () => HttpResponse.json([])),
    )
    renderProductPage(<PrototiposPage />, permittedUser(), ['/prototipos'])
    await userEvent.click(await screen.findByRole('button', { name: /Novo protótipo/ }))
    const form = await screen.findByRole('form', { name: 'Formulário de protótipo' })
    await userEvent.type(within(form).getByLabelText(/Nome em português/), 'Poltrona')
    await userEvent.type(within(form).getByLabelText(/Nome em inglês/), 'Armchair')
    await userEvent.selectOptions(within(form).getByLabelText(/Catálogo/), CATALOG.id)
    await userEvent.type(within(form).getByLabelText(/Altura/), '1')
    await userEvent.type(within(form).getByLabelText(/Largura/), '1')
    const png = new File(['x'], 'frente.png', { type: 'image/png' })
    const webp = new File(['y'], 'lado.webp', { type: 'image/webp' })
    await userEvent.upload(within(form).getByLabelText('Escolher fotos do protótipo'), [png, webp])
    const chosen = within(form).getByRole('list', { name: 'Fotos escolhidas' })
    expect(within(chosen).getByText('Principal')).toBeInTheDocument()
    expect(within(chosen).getAllByRole('listitem')).toHaveLength(2)
    await userEvent.click(within(form).getByRole('button', { name: 'Criar protótipo' }))
    await waitFor(() => expect(order).toEqual(['create', 'photo:proto-PROT-0009', 'photo:proto-PROT-0009']))
    expect(await screen.findByText(/Protótipo PROT-0009 criado/)).toBeInTheDocument()
    expect(screen.queryByRole('list', { name: 'Fotos escolhidas' })).not.toBeInTheDocument()
  })

  it('recusa na tela arquivo que não é imagem aceita ou passa de 5 MB', async () => {
    installProductHandlers({ catalogs: [CATALOG] })
    server.use(listHandler([]))
    renderProductPage(<PrototiposPage />, permittedUser(), ['/prototipos'])
    await userEvent.click(await screen.findByRole('button', { name: /Novo protótipo/ }))
    const form = await screen.findByRole('form', { name: 'Formulário de protótipo' })
    const big = new File([new Uint8Array(5 * 1024 * 1024 + 1)], 'grande.png', { type: 'image/png' })
    const pdf = new File(['z'], 'ficha.pdf', { type: 'application/pdf' })
    await userEvent.upload(within(form).getByLabelText('Escolher fotos do protótipo'), [big, pdf], { applyAccept: false })
    expect(await within(form).findByRole('alert')).toHaveTextContent(/grande\.png: acima de 5 MB/)
    expect(within(form).getByRole('alert')).toHaveTextContent(/ficha\.pdf: use JPG, PNG ou WEBP/)
    expect(within(form).queryByRole('list', { name: 'Fotos escolhidas' })).not.toBeInTheDocument()
  })

  it('subir foto na edição atualiza a lista de protótipos (miniatura nova)', async () => {
    let listed = 0
    const proto = prototypeFixture()
    installProductHandlers({ catalogs: [CATALOG] })
    server.use(
      http.get('*/prototypes', () => {
        listed += 1
        const withPhoto = listed > 1
        return HttpResponse.json([{ ...proto, thumbnail_url: withPhoto ? '/m/nova-t.webp' : null, photo_url: withPhoto ? '/m/nova.png' : null }], {
          headers: { 'X-Total-Count': '1', 'X-Has-More': 'false', 'X-Page-Size': '1' },
        })
      }),
      http.get('*/prototypes/:id/optional-groups', () => HttpResponse.json([])),
      http.post('*/prototypes/:id/photos', () => HttpResponse.json({
        ...proto, photo_url: '/m/nova.png', thumbnail_url: '/m/nova-t.webp', photo_count: 1,
        photos: [{ id: 'ph-1', position: 0, is_primary: true, photo_url: '/m/nova.png', thumbnail_url: '/m/nova-t.webp' }],
      }, { status: 201 })),
    )
    const { container } = renderProductPage(<PrototiposPage />, permittedUser(), ['/prototipos'])
    await userEvent.click(await screen.findByRole('button', { name: /Editar/ }))
    const gallery = await screen.findByRole('region', { name: 'Galeria de fotos' })
    expect(container.querySelector('ul[aria-label="Meus protótipos"] img')).toBeNull()
    await userEvent.upload(within(gallery).getByLabelText('Adicionar fotos à galeria'), new File(['x'], 'a.png', { type: 'image/png' }))
    await waitFor(() => expect(container.querySelector('ul[aria-label="Meus protótipos"] img')).not.toBeNull())
    expect(container.querySelector('ul[aria-label="Meus protótipos"] img')).toHaveAttribute('src', '/m/nova-t.webp')
  })

  it('não envia sem o catálogo', async () => {
    const posts = vi.fn()
    installProductHandlers({ catalogs: [CATALOG] })
    server.use(listHandler([]), http.post('*/prototypes', () => { posts(); return HttpResponse.json({}, { status: 201 }) }))
    renderProductPage(<PrototiposPage />, permittedUser(), ['/prototipos'])
    await userEvent.click(await screen.findByRole('button', { name: /Novo protótipo/ }))
    const form = await screen.findByRole('form', { name: 'Formulário de protótipo' })
    await userEvent.type(within(form).getByLabelText(/Nome em português/), 'A')
    await userEvent.type(within(form).getByLabelText(/Nome em inglês/), 'B')
    await userEvent.type(within(form).getByLabelText(/Altura/), '1')
    await userEvent.type(within(form).getByLabelText(/Largura/), '1')
    await userEvent.click(within(form).getByRole('button', { name: 'Criar protótipo' }))
    expect(posts).not.toHaveBeenCalled()
  })

  it('cria um grupo de opcionais só do protótipo e o aplica a ele', async () => {
    const groupBodies: Array<Record<string, unknown>> = []
    const patches: Array<Record<string, unknown>> = []
    const proto = prototypeFixture()
    installProductHandlers({ catalogs: [CATALOG] })
    server.use(
      listHandler([proto]),
      http.get('*/prototypes/:id/optional-groups', () => HttpResponse.json([])),
      http.post('*/prototypes/:id/optional-groups', async ({ request }) => {
        const body = await request.json() as Record<string, unknown>
        groupBodies.push(body)
        return HttpResponse.json({ id: 'grp-1', code: 'PROT-0001-TAMPO', name: body.name, options: [{ id: 'o1', name: 'Carvalho' }] }, { status: 201 })
      }),
      http.patch('*/prototypes/:id', async ({ request }) => {
        const body = await request.json() as Record<string, unknown>
        patches.push(body)
        return HttpResponse.json({ ...proto, optional_applications: [] })
      }),
    )
    renderProductPage(<PrototiposPage />, permittedUser(), ['/prototipos'])
    await userEvent.click(await screen.findByRole('button', { name: /Editar/ }))
    const section = await screen.findByRole('region', { name: 'Grupos só deste protótipo' })
    await userEvent.click(within(section).getByRole('button', { name: /Novo grupo/ }))
    await userEvent.type(within(section).getByLabelText(/Nome do grupo/), 'Tampo')
    await userEvent.type(within(section).getByLabelText(/Opções/), 'Carvalho{enter}Nogueira')
    await userEvent.click(within(section).getByRole('button', { name: 'Salvar grupo' }))
    await waitFor(() => expect(groupBodies).toHaveLength(1))
    expect(groupBodies[0]).toEqual({ name: 'Tampo', options: [{ name: 'Carvalho' }, { name: 'Nogueira' }] })
    await waitFor(() => expect(patches).toHaveLength(1))
    expect(patches[0].optional_applications).toEqual([
      expect.objectContaining({ category_id: 'grp-1', name: 'Tampo', allow_all: true }),
    ])
  })
})

describe('ProdutosPage — Visualizar protótipo', () => {
  it('não mostra o botão sem a permissão', async () => {
    installProductHandlers({ products: [productFixture('EU')] })
    renderProductPage(<ProdutosPage />, permittedUser(false), ['/produtos'])
    expect(await screen.findByText('Mesa PT')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Visualizar protótipo/ })).not.toBeInTheDocument()
  })

  it('com a permissão, alterna o catálogo pelos próprios protótipos', async () => {
    installProductHandlers({ products: [productFixture('EU')] })
    server.use(listHandler([prototypeFixture('PROT-0003', { description: 'Mesa protótipo' })]))
    renderProductPage(<ProdutosPage />, permittedUser(), ['/produtos'])
    expect(await screen.findByText('Mesa PT')).toBeInTheDocument()
    const toggle = screen.getByRole('button', { name: /Visualizar protótipo/ })
    expect(toggle).toHaveAttribute('aria-pressed', 'false')
    await userEvent.click(toggle)
    expect(await screen.findByText('Mesa protótipo')).toBeInTheDocument()
    expect(screen.getByText('PROT-0003')).toBeInTheDocument()
    expect(screen.queryByText('Mesa PT')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Visualizar protótipo/ })).toHaveAttribute('aria-pressed', 'true')
    await userEvent.click(screen.getByRole('button', { name: /Visualizar protótipo/ }))
    expect(await screen.findByText('Mesa PT')).toBeInTheDocument()
  })

  it('o catálogo comum não chama a rota de protótipos', async () => {
    const calls = vi.fn()
    installProductHandlers({ products: [productFixture('EU')] })
    server.use(http.get('*/prototypes', () => { calls(); return HttpResponse.json([]) }))
    renderProductPage(<ProdutosPage />, permittedUser(), ['/produtos'])
    expect(await screen.findByText('Mesa PT')).toBeInTheDocument()
    expect(calls).not.toHaveBeenCalled()
  })
})
