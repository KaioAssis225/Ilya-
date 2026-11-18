// Gate de auditoria de dependências do CI: equivale a `npm audit --audit-level=high`,
// exceto pelos advisórios da lista IGNORED abaixo.
//
// O `npm audit` não tem allowlist nativa. Este script lê `npm audit --json`,
// junta os advisórios (as entradas `via` que são objetos) e reprova se sobrar
// algum de severidade high/critical fora da lista. Pacotes que só aparecem por
// herdar um advisório ignorado (fdir, tinyglobby, vite…) não contam por si, pois
// o alerta deles vem sempre de um advisório.
//
// Exceções devem ser raras, com motivo e critério de saída.
import { spawnSync } from 'node:child_process'

const IGNORED = {
  // picomatch ReDoS (todas as versões <= 4.0.7; não há versão corrigida; a 4.0.7 é
  // a mais recente). Entra só no build/testes via vite -> tinyglobby -> fdir, com
  // globs da configuração e não de entrada de usuário, e não vai para o bundle
  // servido. Remover quando o picomatch publicar a correção: `npm audit fix`
  // passará a resolver e este item deve sair daqui.
  'GHSA-fc5q-39xc-vjpf': 'picomatch ReDoS sem versão corrigida (decisão do produto)',
}

const BLOCKING = new Set(['high', 'critical'])

const result = spawnSync('npm', ['audit', '--json'], { encoding: 'utf8', shell: process.platform === 'win32', maxBuffer: 64 * 1024 * 1024 })
let report
try {
  report = JSON.parse(result.stdout)
} catch {
  console.error('Não foi possível ler a saída de `npm audit --json`:')
  console.error(result.stdout || result.stderr)
  process.exit(2)
}
if (report.error) {
  console.error(`npm audit falhou: ${report.error.summary ?? JSON.stringify(report.error)}`)
  process.exit(2)
}

const advisories = new Map()
for (const vuln of Object.values(report.vulnerabilities ?? {})) {
  for (const via of vuln.via ?? []) {
    if (typeof via !== 'object' || via === null) continue
    const id = String(via.url ?? '').split('/').pop() || String(via.source)
    advisories.set(id, { id, severity: via.severity, title: via.title, pkg: via.name })
  }
}

const blocking = []
for (const advisory of advisories.values()) {
  if (!BLOCKING.has(advisory.severity)) continue
  if (advisory.id in IGNORED) {
    console.log(`Ignorado: ${advisory.id} (${advisory.pkg}, ${advisory.severity}) — ${IGNORED[advisory.id]}`)
    continue
  }
  blocking.push(advisory)
}

if (blocking.length > 0) {
  console.error('Vulnerabilidades de severidade alta/crítica sem exceção:')
  for (const advisory of blocking) {
    console.error(`- ${advisory.id} (${advisory.pkg}, ${advisory.severity}): ${advisory.title}`)
  }
  console.error('Rode `npm audit` para os detalhes e `npm audit fix` para corrigir.')
  process.exit(1)
}
console.log('Auditoria de dependências OK (nenhum alerta alto/crítico fora da lista de exceções).')
