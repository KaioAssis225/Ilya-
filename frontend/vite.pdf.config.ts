import { createHash } from 'node:crypto'
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { defineConfig, type Plugin } from 'vite'

const frontendDir = path.dirname(fileURLToPath(import.meta.url))
const outDir = path.resolve(frontendDir, '../backend/app/pdf_bundle')

function pdfBundleMetaPlugin(): Plugin {
  return {
    name: 'ilya-pdf-bundle-meta',
    writeBundle(_options, bundle) {
      const sourceSet = new Set<string>()
      for (const item of Object.values(bundle)) {
        if (item.type !== 'chunk') continue
        for (const rawId of Object.keys(item.modules)) {
          const cleanId = rawId.replace(/\0/g, '').split('?')[0].replace(/\\/g, '/')
          if (!cleanId.includes('/src/') || cleanId.includes('node_modules')) continue
          const relPath = path.relative(frontendDir, cleanId).replace(/\\/g, '/')
          if (relPath.startsWith('src/') && existsSync(path.resolve(frontendDir, relPath))) {
            sourceSet.add(relPath)
          }
        }
      }

      const sources = Array.from(sourceSet).sort()
      const jspdfPkgPath = path.resolve(frontendDir, 'node_modules/jspdf/package.json')
      const jspdfPkg = JSON.parse(readFileSync(jspdfPkgPath, 'utf8')) as { version: string }
      const jspdfVersion = jspdfPkg.version

      const hash = createHash('sha256')
      for (const source of sources) {
        const content = readFileSync(path.resolve(frontendDir, source), 'utf8').replace(/\r\n/g, '\n')
        hash.update(`${source}\n${content}`)
      }
      hash.update(jspdfVersion)

      const meta = {
        sources,
        jspdf_version: jspdfVersion,
        sha256: hash.digest('hex'),
      }

      mkdirSync(outDir, { recursive: true })
      writeFileSync(
        path.resolve(outDir, 'pdf-render.meta.json'),
        `${JSON.stringify(meta, null, 2)}\n`,
        'utf8',
      )
    },
  }
}

export default defineConfig({
  plugins: [pdfBundleMetaPlugin()],
  // Sem isto o Vite copia public/ (favicons etc.) para o diretório do bundle.
  publicDir: false,
  define: {
    'process.env.NODE_ENV': '"production"',
  },
  build: {
    outDir,
    emptyOutDir: false,
    minify: true,
    assetsInlineLimit: 10 * 1024 * 1024,
    lib: {
      entry: 'src/pdf-render/entry.ts',
      formats: ['iife'],
      name: 'IlyaPdfRender',
      fileName: () => 'pdf-render.js',
    },
    rollupOptions: {
      output: {
        inlineDynamicImports: true,
      },
    },
  },
})
