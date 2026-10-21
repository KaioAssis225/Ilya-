import { describe, expect, it } from 'vitest'
import { csvCell, csvRow } from './csv'

describe('csvCell', () => {
  it('neutraliza texto que o Excel executaria como fórmula', () => {
    for (const value of ['=HYPERLINK("http://x")', '+1+1', '-2+3', '@SUM(A1)', '\tx', '\rx']) {
      expect(csvCell(value).startsWith(`"'`)).toBe(true)
    }
  })

  it('isola separador, aspas e quebra de linha dentro da célula', () => {
    expect(csvCell('Silva; "Rep" \n Lda')).toBe('"Silva; ""Rep"" \n Lda"')
  })

  it('mantém números como números, inclusive negativos', () => {
    expect(csvCell(-12.5)).toBe('-12.5')
    expect(csvCell(3)).toBe('3')
  })
})

describe('csvRow', () => {
  it('junta as células com ponto e vírgula', () => {
    expect(csvRow(['=cmd', 2])).toBe(`"'=cmd";2`)
  })
})
