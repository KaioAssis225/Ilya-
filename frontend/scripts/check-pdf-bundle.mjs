// Verifica se o bundle do PDF do servidor (`backend/app/pdf_bundle/pdf-render.js`)
// está sincronizado com as fontes em `frontend/src/` e a versão do `jspdf`.
import { createHash } from 'node:crypto'
import { existsSync, readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const scriptDir = path.dirname(fileURLToPath(import.meta.url))
const frontendDir = path.resolve(scriptDir, '..')
const bundleDir = path.resolve(frontendDir, '../backend/app/pdf_bundle')
const bundleJsPath = path.resolve(bundleDir, 'pdf-render.js')
const metaPath = path.resolve(bundleDir, 'pdf-render.meta.json')
const jspdfPkgPath = path.resolve(frontendDir, 'node_modules/jspdf/package.json')

function fail(reason) {
  console.error(`Bundle do PDF desatualizado: ${reason}`)
  console.error('Atualize com: npm run build:pdf-bundle')
  process.exit(1)
}

if (!existsSync(metaPath)) {
  fail('arquivo pdf-render.meta.json ausente')
}

if (!existsSync(bundleJsPath)) {
  fail('arquivo pdf-render.js ausente')
}

if (!existsSync(jspdfPkgPath)) {
  fail('node_modules/jspdf/package.json ausente')
}

const meta = JSON.parse(readFileSync(metaPath, 'utf8'))
const jspdfPkg = JSON.parse(readFileSync(jspdfPkgPath, 'utf8'))
const jspdfVersion = jspdfPkg.version

if (!Array.isArray(meta.sources) || meta.sources.length === 0) {
  fail('lista de fontes inválida em pdf-render.meta.json')
}

const missingSources = []
const hash = createHash('sha256')

for (const source of meta.sources) {
  const sourcePath = path.resolve(frontendDir, source)
  if (!existsSync(sourcePath)) {
    missingSources.push(source)
    continue
  }
  const content = readFileSync(sourcePath, 'utf8').replace(/\r\n/g, '\n')
  hash.update(`${source}\n${content}`)
}

if (missingSources.length > 0) {
  fail(`fonte(s) ausente(s): ${missingSources.join(', ')}`)
}

if (meta.jspdf_version !== jspdfVersion) {
  fail(`versão do jspdf mudou (${meta.jspdf_version} -> ${jspdfVersion}); fontes: ${meta.sources.join(', ')}`)
}

hash.update(jspdfVersion)
const calculatedSha256 = hash.digest('hex')

if (calculatedSha256 !== meta.sha256) {
  fail(`hash divergente (esperado ${meta.sha256}, calculado ${calculatedSha256}) nas fontes monitoradas: ${meta.sources.join(', ')}`)
}

console.log('pdf bundle em dia')
process.exit(0)
