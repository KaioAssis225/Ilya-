import { useEffect, useState } from 'react'
import { FolderOpen } from 'lucide-react'
import { useLocale } from '../hooks/useLocale'
import {
  clearDestinationFolder,
  isFolderPickerSupported,
  loadDestinationFolderName,
  pickDestinationFolder,
} from '../lib/pdfDestination'

const ACTION_CLASS =
  'text-gold hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-gold disabled:text-muted-3 disabled:no-underline disabled:cursor-not-allowed'

/**
 * Pasta onde os PDFs de orçamento são gravados. Sem pasta escolhida (ou fora do
 * Chrome/Edge no computador) o PDF segue para Downloads, como antes.
 */
export function PdfDestinationControl({ userKey }: { userKey: string }) {
  const { locale } = useLocale()
  const isEnglish = locale === 'en-GB'
  const supported = isFolderPickerSupported()
  const [folderName, setFolderName] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    loadDestinationFolderName(userKey).then((name) => {
      if (!cancelled) setFolderName(name)
    })
    return () => {
      cancelled = true
    }
  }, [userKey])

  async function handlePick() {
    setBusy(true)
    setMessage(null)
    const result = await pickDestinationFolder(userKey)
    if (result.status === 'chosen') {
      setFolderName(result.folderName)
    } else if (result.status === 'error') {
      setMessage(isEnglish ? 'Could not remember the folder in this browser.' : 'Não foi possível guardar a pasta neste navegador.')
    }
    setBusy(false)
  }

  async function handleClear() {
    setBusy(true)
    setMessage(null)
    if (await clearDestinationFolder(userKey)) {
      setFolderName(null)
    } else {
      setMessage(isEnglish ? 'Could not clear the folder.' : 'Não foi possível limpar a pasta.')
    }
    setBusy(false)
  }

  const hint = isEnglish ? 'Available in Chrome/Edge on desktop' : 'Disponível no Chrome/Edge no computador'

  return (
    <div data-testid="pdf-destination" className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted">
      <FolderOpen className="w-3.5 h-3.5" aria-hidden="true" />
      <span>{isEnglish ? 'Save folder:' : 'Pasta de destino:'}</span>
      {folderName ? (
        <span className="text-ink font-medium max-w-[16rem] truncate" title={folderName}>
          {folderName}
        </span>
      ) : (
        <span className="text-ink font-medium">{isEnglish ? 'Downloads (default)' : 'Downloads (padrão)'}</span>
      )}

      {!supported ? (
        <>
          <button type="button" disabled title={hint} className="text-muted-3 cursor-not-allowed">
            {isEnglish ? 'Choose folder' : 'Escolher pasta'}
          </button>
          <span aria-hidden="true">·</span>
          <span>{hint}</span>
        </>
      ) : folderName === null ? (
        <button type="button" onClick={handlePick} disabled={busy} className={ACTION_CLASS}>
          {isEnglish ? 'Choose folder' : 'Escolher pasta'}
        </button>
      ) : (
        <>
          <button type="button" onClick={handlePick} disabled={busy} className={ACTION_CLASS}>
            {isEnglish ? 'Change' : 'Alterar'}
          </button>
          <span aria-hidden="true">·</span>
          <button type="button" onClick={handleClear} disabled={busy} className={ACTION_CLASS}>
            {isEnglish ? 'Use Downloads' : 'Usar Downloads'}
          </button>
        </>
      )}

      {message && (
        <span role="status" className="text-danger">
          {message}
        </span>
      )}
    </div>
  )
}
