import { describe, expect, it } from 'vitest'

import {
  MAX_PRODUCT_DIMENSION_M,
  PRODUCT_DIMENSION_LIMIT_MESSAGE,
  exceedsDimensionLimit,
  hasDimensionOverLimit,
} from './productMeasureLimit'
import { translateCadastro } from './cadastroText'

describe('limite de medidas de produto', () => {
  it('usa 20 m e uma mensagem que ensina a converter mm', () => {
    expect(MAX_PRODUCT_DIMENSION_M).toBe(20)
    expect(PRODUCT_DIMENSION_LIMIT_MESSAGE).toContain('20 m')
    expect(PRODUCT_DIMENSION_LIMIT_MESSAGE).toContain('470 mm = 0,47')
  })

  it('aceita até 20 m e recusa acima', () => {
    expect(exceedsDimensionLimit(0.47)).toBe(false)
    expect(exceedsDimensionLimit(20)).toBe(false)
    expect(exceedsDimensionLimit('20')).toBe(false)
    expect(exceedsDimensionLimit(20.01)).toBe(true)
    expect(exceedsDimensionLimit(470)).toBe(true)
    expect(exceedsDimensionLimit('780')).toBe(true)
  })

  it('ignora valores vazios ou não numéricos', () => {
    expect(exceedsDimensionLimit(null)).toBe(false)
    expect(exceedsDimensionLimit(undefined)).toBe(false)
    expect(exceedsDimensionLimit('')).toBe(false)
    expect(exceedsDimensionLimit(Number.NaN)).toBe(false)
  })

  it('confere altura, largura e profundidade, e ignora a profundidade do redondo', () => {
    expect(hasDimensionOverLimit({ altura: 0.78, largura: 0.47, profundidade: 0.49 }, false)).toBe(false)
    expect(hasDimensionOverLimit({ altura: 780, largura: 0.47, profundidade: 0.49 }, false)).toBe(true)
    expect(hasDimensionOverLimit({ altura: 0.78, largura: 470, profundidade: 0.49 }, false)).toBe(true)
    expect(hasDimensionOverLimit({ altura: 0.78, largura: 0.47, profundidade: 490 }, false)).toBe(true)
    expect(hasDimensionOverLimit({ altura: 0.78, largura: 0.47, profundidade: 490 }, true)).toBe(false)
  })

  it('traduz a mensagem no mercado EU e mantém o português no BR', () => {
    expect(translateCadastro('en-GB', PRODUCT_DIMENSION_LIMIT_MESSAGE)).toBe(
      'Measurement above 20 m — measurements are in metres (e.g. 470 mm = 0.47).',
    )
    expect(translateCadastro('pt-PT', PRODUCT_DIMENSION_LIMIT_MESSAGE)).toBe(PRODUCT_DIMENSION_LIMIT_MESSAGE)
  })
})
