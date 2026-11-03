import { describe, it, expect } from 'vitest'
import { resolveOrderStage, stageLabel, describeStageChange } from './orderStage'

describe('resolveOrderStage', () => {
  it('retorna null para pedido não finalizado', () => {
    expect(resolveOrderStage({ is_finalized: false, is_cancelled: false })).toBeNull()
  })

  it('retorna null para pedido cancelado', () => {
    expect(resolveOrderStage({ is_finalized: true, is_cancelled: true })).toBeNull()
  })

  it('retorna production para finalizado sem etapa', () => {
    expect(resolveOrderStage({ is_finalized: true, is_cancelled: false })).toBe('production')
  })

  it('retorna delivered quando a etapa é delivered', () => {
    expect(resolveOrderStage({ is_finalized: true, is_cancelled: false, order_stage: 'delivered' })).toBe('delivered')
  })
})

describe('stageLabel', () => {
  it('traduz para português', () => {
    expect(stageLabel('production', false)).toBe('Produção')
    expect(stageLabel('delivered', false)).toBe('Entregue')
  })

  it('traduz para inglês', () => {
    expect(stageLabel('production', true)).toBe('In production')
    expect(stageLabel('delivered', true)).toBe('Delivered')
  })
})

describe('describeStageChange', () => {
  it('converte production -> delivered em português', () => {
    expect(describeStageChange('production -> delivered', false)).toBe('Produção → Entregue')
  })

  it('converte delivered -> production em inglês', () => {
    expect(describeStageChange('delivered -> production', true)).toBe('Delivered → In production')
  })

  it('retorna null para detalhes nulos', () => {
    expect(describeStageChange(null, false)).toBeNull()
  })

  it('retorna null para formato inválido', () => {
    expect(describeStageChange('foo -> bar', false)).toBeNull()
  })
})
