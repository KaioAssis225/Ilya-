/** Bloco 74: identifica "conjuntos" por substring case-insensitive no nome do
 * tipo, em vez de exigir o valor exato "Conjunto". Cobre tipos como
 * "Conjunto de Jantar" ou "Conjuntos", ativando a modelagem de componentes livres. */
export function isConjuntoType(type: string | null | undefined): boolean {
  return (type ?? '').toLowerCase().includes('conjunto')
}
