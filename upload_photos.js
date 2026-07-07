#!/usr/bin/env node
/**
 * Bloco 70 — Upload de Fotos em Lote
 *
 * Faz login na API de produção do Ilya, lê uma pasta local de fotos, identifica
 * o produto por SKU a partir do nome do arquivo (ex.: "IML0001.png" -> produto
 * de codigo "IML0001") e envia cada foto para /api/v1/products/{id}/upload-photo.
 *
 * Uso:
 *   ILYA_EMAIL=admin@ilya.com ILYA_PASSWORD="sua-senha" node upload_photos.js
 *   node upload_photos.js --email admin@ilya.com --password "sua-senha" --dir "C:\caminho\fotos"
 *
 * Requer Node 18+ (usa fetch/FormData/Blob nativos, sem dependencias externas).
 */

const fs = require('fs')
const path = require('path')
const readline = require('readline')

const API_BASE_URL = process.env.ILYA_API_URL || 'https://ilya-production-7857.up.railway.app'
const DEFAULT_PHOTOS_DIR = 'C:\\Users\\matheus.cardoso\\Documents\\Subir\\fotos'
const ALLOWED_EXTENSIONS = new Set(['jpg', 'jpeg', 'png', 'webp'])
const PAGE_SIZE = 200 // le=200 (Bloco 68, item 16)

function parseArgs(argv) {
  const args = { email: null, password: null, dir: null }
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--email') args.email = argv[++i]
    else if (argv[i] === '--password') args.password = argv[++i]
    else if (argv[i] === '--dir') args.dir = argv[++i]
  }
  return args
}

function prompt(question) {
  return new Promise((resolve) => {
    const rl = readline.createInterface({ input: process.stdin, output: process.stdout })
    rl.question(question, (answer) => { rl.close(); resolve(answer.trim()) })
  })
}

function skuFromFilename(filename) {
  return path.basename(filename, path.extname(filename)).trim().toUpperCase()
}

async function login(email, password) {
  const res = await fetch(`${API_BASE_URL}/api/v1/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ identifier: email, password }),
  })
  if (!res.ok) {
    const detail = await res.text()
    throw new Error(`Falha no login (${res.status}): ${detail}`)
  }
  const data = await res.json()
  return data.access_token
}

async function fetchAllProducts(token) {
  const products = []
  let skip = 0
  for (;;) {
    const res = await fetch(`${API_BASE_URL}/api/v1/products?skip=${skip}&limit=${PAGE_SIZE}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (!res.ok) throw new Error(`Falha ao listar produtos (${res.status}): ${await res.text()}`)
    const page = await res.json()
    products.push(...page)
    if (page.length < PAGE_SIZE) break
    skip += PAGE_SIZE
  }
  return products
}

async function uploadPhoto(token, productId, filePath) {
  const buffer = fs.readFileSync(filePath)
  const ext = path.extname(filePath).slice(1).toLowerCase()
  const mime = { jpg: 'image/jpeg', jpeg: 'image/jpeg', png: 'image/png', webp: 'image/webp' }[ext] || 'application/octet-stream'
  const form = new FormData()
  form.append('file', new Blob([buffer], { type: mime }), path.basename(filePath))

  const res = await fetch(`${API_BASE_URL}/api/v1/products/${productId}/upload-photo`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  })
  if (!res.ok) {
    const detail = await res.text()
    throw new Error(`${res.status}: ${detail}`)
  }
  return res.json()
}

async function main() {
  const args = parseArgs(process.argv.slice(2))
  const email = args.email || process.env.ILYA_EMAIL || (await prompt('E-mail/usuário: '))
  const password = args.password || process.env.ILYA_PASSWORD || (await prompt('Senha: '))
  const photosDir = args.dir || DEFAULT_PHOTOS_DIR

  if (!fs.existsSync(photosDir)) {
    console.error(`Pasta não encontrada: ${photosDir}`)
    process.exit(1)
  }

  console.log(`Fazendo login em ${API_BASE_URL}...`)
  const token = await login(email, password)

  console.log('Carregando lista de produtos...')
  const products = await fetchAllProducts(token)
  const bySku = new Map(products.map((p) => [p.product_code.toUpperCase(), p]))
  console.log(`${products.length} produtos carregados.`)

  const files = fs.readdirSync(photosDir).filter((f) => ALLOWED_EXTENSIONS.has(path.extname(f).slice(1).toLowerCase()))
  console.log(`${files.length} arquivo(s) de imagem encontrados em ${photosDir}.`)

  let uploaded = 0
  const skipped = []
  const errors = []

  for (const file of files) {
    const sku = skuFromFilename(file)
    const product = bySku.get(sku)
    if (!product) {
      skipped.push(`${file} (SKU '${sku}' não encontrado no cadastro)`)
      continue
    }
    const filePath = path.join(photosDir, file)
    try {
      await uploadPhoto(token, product.id, filePath)
      uploaded++
      console.log(`✓ ${file} -> ${sku}`)
    } catch (err) {
      errors.push(`${file} (${sku}): ${err.message}`)
      console.log(`✗ ${file} -> ${sku}: ${err.message}`)
    }
  }

  console.log('\n── Resumo ──────────────────────────')
  console.log(`Enviadas: ${uploaded}`)
  console.log(`Ignoradas (sem SKU correspondente): ${skipped.length}`)
  console.log(`Erros: ${errors.length}`)
  if (skipped.length) {
    console.log('\nArquivos ignorados:')
    skipped.forEach((s) => console.log(`  - ${s}`))
  }
  if (errors.length) {
    console.log('\nErros:')
    errors.forEach((e) => console.log(`  - ${e}`))
    process.exitCode = 1
  }
}

main().catch((err) => {
  console.error('Erro fatal:', err.message)
  process.exit(1)
})
