// Excel e LibreOffice executam como fórmula a célula que começa com estes
// caracteres; nomes e descrições vêm de cadastros editáveis por terceiros.
const FORMULA_START = /^[=+\-@\t\r]/

/** Célula de CSV separado por `;`, segura para abrir em planilha. */
export function csvCell(value: string | number): string {
  if (typeof value === 'number') return String(value)
  const text = FORMULA_START.test(value) ? `'${value}` : value
  return `"${text.replace(/"/g, '""')}"`
}

export function csvRow(cells: Array<string | number>): string {
  return cells.map(csvCell).join(';')
}
