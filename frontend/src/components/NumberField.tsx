import { useState, type InputHTMLAttributes } from 'react'

// Campo numérico que não deixa o "0" grudado no começo da digitação.
//
// Um `<input type="number">` controlado por `value={0}` mostra "0"; ao digitar,
// o usuário acaba com "05" ou "50" e precisa apagar o zero na mão. Aqui o campo
// nasce VAZIO quando o valor é 0 e, a partir do primeiro toque, passa a exibir
// exatamente o texto digitado — então "0", "0.5" e "10." funcionam sem o campo
// se reescrever no meio da digitação.
//
// O rascunho vale enquanto representar o valor atual do formulário. Quando o
// formulário muda por fora (abriu outro produto, resetou o form), ele deixa de
// bater e o campo volta a espelhar o valor canônico.

type NumberFieldProps = Omit<
  InputHTMLAttributes<HTMLInputElement>,
  'value' | 'onChange' | 'type'
> & {
  value: number | null | undefined
  onValueChange: (value: number) => void
}

export function NumberField({ value, onValueChange, ...props }: NumberFieldProps) {
  const [draft, setDraft] = useState<string | null>(null)

  const current = value ?? 0
  const draftMatchesValue =
    draft !== null && (draft === '' ? current === 0 : Number(draft) === current)

  return (
    <input
      {...props}
      type="number"
      value={draftMatchesValue ? (draft as string) : current === 0 ? '' : String(current)}
      onChange={(e) => {
        const text = e.target.value
        setDraft(text)
        // O browser devolve '' para texto ainda inválido (ex.: "1e"); nesse
        // caso o formulário fica em 0 sem perder o que está escrito no campo.
        const parsed = Number(text)
        onValueChange(text === '' || Number.isNaN(parsed) ? 0 : parsed)
      }}
    />
  )
}
