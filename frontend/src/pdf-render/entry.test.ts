import assert from 'node:assert/strict'
import { test, vi } from 'vitest'
import type { OrderPdfSnapshot } from '../lib/orderPdfSnapshot.ts'

vi.mock('jspdf', () => {
  class MockJsPDF {
    internal = {
      pageSize: {
        getWidth: () => 210,
      },
    }
    setDrawColor() {}
    setLineWidth() {}
    line() {}
    setFont() {}
    setFontSize() {}
    setTextColor() {}
    setFillColor() {}
    roundedRect() {}
    rect() {}
    saveGraphicsState() {}
    restoreGraphicsState() {}
    clip() {}
    discardPath() {}
    addPage() {}
    getNumberOfPages() { return 1 }
    setPage() {}
    addImage() {}
    splitTextToSize(text: string) {
      return [String(text)]
    }
    text() {}
    save() {}
    output() {
      return new Uint8Array([37, 80, 68, 70]).buffer
    }
  }
  return { default: MockJsPDF }
})

import './entry.ts'

const NOW = '2026-04-19T12:00:00.000Z'

function makeMinimalSnapshot(): OrderPdfSnapshot {
  return {
    schema_version: 2,
    locale: 'pt-BR',
    order: {
      id: 'ord-1',
      code: 'PED-0001',
      orc_id: 'ORC-0001',
      market_code: 'BR',
      price_list_code: 'BR_LOJISTA',
      currency: 'BRL',
      locale: 'pt-BR',
      client_id: 'cli-1',
      rep_id: null,
      total_value: 5000,
      total_ipi: 250,
      total_with_ipi: 5250,
      is_finalized: true,
      is_cancelled: false,
      finalized_at: NOW,
      cancelled_at: null,
      external_code: null,
      notes: null,
      items: [
        {
          id: 'item-1',
          order_id: 'ord-1',
          product_code: 'POL-001',
          description: 'Poltrona Ilya',
          is_circular: false,
          altura: 80,
          largura: 75,
          profundidade: 82,
          opt_categories: {},
          optional_choices: [],
          qty: 1,
          unit_price: 5000,
          discount: 0,
          ipi_rate: 5,
          ipi_value: 250,
          tax_label: 'IPI',
          currency: 'BRL',
          observacao: null,
          created_at: NOW,
          updated_at: NOW,
        },
      ],
      history: [],
      created_at: NOW,
      updated_at: NOW,
    },
    client: {
      id: 'cli-1',
      name: 'Cliente Teste',
      phone: '+55 11 99999-0000',
      email: 'cliente@example.com',
      cpf_cnpj: '12.345.678/0001-90',
      cep: '01310-100',
      numero: '1000',
      address: 'Av. Paulista',
      city: 'São Paulo',
      state: 'SP',
      country: 'BR',
      region: null,
      tax_id: null,
      market_code: 'BR',
      price_profile: 'lojista',
      max_discount: 10,
      rep_id: null,
      created_at: NOW,
      updated_at: NOW,
      last_activity_at: NOW,
    },
    representative: null,
    products: [
      {
        product_code: 'POL-001',
        type: 'Poltronas',
        is_set: false,
        components: [],
        thumbnail_url: null,
        photo_url: null,
      },
    ],
    category_labels: {},
  }
}

test('importar entry.ts registra window.ilyaRenderOrderPdf e devolve PDF em base64 para snapshot v2', async () => {
  assert.equal(typeof window.ilyaRenderOrderPdf, 'function')

  const base64 = await window.ilyaRenderOrderPdf!(makeMinimalSnapshot())
  assert.equal(base64, 'JVBERg==')
})

test('window.ilyaRenderOrderPdf rejeita schema_version diferente de 2 com unsupported_snapshot_version', async () => {
  const invalidSnapshot = {
    ...makeMinimalSnapshot(),
    schema_version: 1,
  } as unknown as OrderPdfSnapshot

  await assert.rejects(
    async () => {
      await window.ilyaRenderOrderPdf!(invalidSnapshot)
    },
    { message: 'unsupported_snapshot_version' },
  )
})
