import { useEffect, useId, useRef, useState, type CSSProperties, type KeyboardEvent } from 'react'
import { createPortal } from 'react-dom'
import { ChevronDown } from 'lucide-react'

export interface OptionalComboboxOption {
  value: string
  label: string
  photoUrl: string | null
  previewUrl?: string | null
}

interface OptionalComboboxProps {
  label: string
  value: string
  options: OptionalComboboxOption[]
  placeholder: string
  onChange: (value: string) => void
  onPreview?: (photoUrl: string, label: string) => void
  invalid?: boolean
  className?: string
}

interface ListPosition {
  left: number
  width: number
  maxHeight: number
  top?: number
  bottom?: number
}

const LIST_GAP = 4
const LIST_MAX_HEIGHT = 320
const VIEWPORT_GUTTER = 8

export function OptionalCombobox({
  label,
  value,
  options,
  placeholder,
  onChange,
  onPreview,
  invalid = false,
  className = '',
}: OptionalComboboxProps) {
  const [open, setOpen] = useState(false)
  const [activeIndex, setActiveIndex] = useState(0)
  const [position, setPosition] = useState<ListPosition | null>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const listRef = useRef<HTMLUListElement>(null)
  const listboxId = useId()
  const allOptions: OptionalComboboxOption[] = [
    { value: '', label: placeholder, photoUrl: null },
    ...options,
  ]
  const selectedIndex = Math.max(0, allOptions.findIndex(option => option.value === value))
  const selected = allOptions[selectedIndex]

  function openList(index = selectedIndex) {
    const rect = triggerRef.current?.getBoundingClientRect()
    if (!rect) return

    const viewportWidth = window.innerWidth
    const viewportHeight = window.innerHeight
    const width = Math.min(320, Math.max(220, rect.width), viewportWidth - VIEWPORT_GUTTER * 2)
    const left = Math.min(
      Math.max(VIEWPORT_GUTTER, rect.left),
      Math.max(VIEWPORT_GUTTER, viewportWidth - width - VIEWPORT_GUTTER),
    )
    const spaceBelow = viewportHeight - rect.bottom - VIEWPORT_GUTTER
    const spaceAbove = rect.top - VIEWPORT_GUTTER
    const opensUp = spaceBelow < LIST_MAX_HEIGHT && spaceAbove > spaceBelow

    setPosition({
      left,
      width,
      maxHeight: Math.max(44, Math.min(LIST_MAX_HEIGHT, opensUp ? spaceAbove - LIST_GAP : spaceBelow - LIST_GAP)),
      ...(opensUp
        ? { bottom: viewportHeight - rect.top + LIST_GAP }
        : { top: rect.bottom + LIST_GAP }),
    })
    setActiveIndex(index)
    setOpen(true)
  }

  function closeList({ restoreFocus = false } = {}) {
    setOpen(false)
    setPosition(null)
    if (restoreFocus) triggerRef.current?.focus()
  }

  function choose(option: OptionalComboboxOption) {
    onChange(option.value)
    closeList()
    const previewUrl = option.previewUrl ?? option.photoUrl
    if (previewUrl) onPreview?.(previewUrl, option.label)
  }

  useEffect(() => {
    if (!open) return

    const handlePointerDown = (event: PointerEvent) => {
      const target = event.target as Node
      if (!triggerRef.current?.contains(target) && !listRef.current?.contains(target)) closeList()
    }
    const handleScroll = (event: Event) => {
      const target = event.target
      if (target instanceof Node && listRef.current?.contains(target)) return
      closeList()
    }
    const handleResize = () => closeList()

    document.addEventListener('pointerdown', handlePointerDown)
    window.addEventListener('scroll', handleScroll, true)
    window.addEventListener('resize', handleResize)
    return () => {
      document.removeEventListener('pointerdown', handlePointerDown)
      window.removeEventListener('scroll', handleScroll, true)
      window.removeEventListener('resize', handleResize)
    }
  }, [open])

  useEffect(() => {
    if (!open) return
    const activeOption = document.getElementById(`${listboxId}-option-${activeIndex}`)
    activeOption?.scrollIntoView?.({ block: 'nearest' })
  }, [activeIndex, listboxId, open])

  function handleKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
    if (event.key === 'Tab') {
      if (open) closeList()
      return
    }

    if (event.key === 'Escape') {
      if (open) {
        event.preventDefault()
        closeList({ restoreFocus: true })
      }
      return
    }

    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      if (open) choose(allOptions[activeIndex])
      else openList()
      return
    }

    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault()
      if (!open) {
        openList(event.key === 'ArrowUp' && selectedIndex === 0 ? allOptions.length - 1 : selectedIndex)
        return
      }
      const direction = event.key === 'ArrowDown' ? 1 : -1
      setActiveIndex(current => Math.min(allOptions.length - 1, Math.max(0, current + direction)))
      return
    }

    if (open && (event.key === 'Home' || event.key === 'End')) {
      event.preventDefault()
      setActiveIndex(event.key === 'Home' ? 0 : allOptions.length - 1)
      return
    }

    if (event.key.length === 1 && !event.altKey && !event.ctrlKey && !event.metaKey) {
      const matchIndex = allOptions.findIndex((option, index) => (
        index > 0 && option.label.toLocaleLowerCase().startsWith(event.key.toLocaleLowerCase())
      ))
      if (matchIndex >= 0) {
        event.preventDefault()
        if (!open) openList(matchIndex)
        else setActiveIndex(matchIndex)
      }
    }
  }

  const listStyle: CSSProperties | undefined = position
    ? {
        left: position.left,
        width: position.width,
        maxHeight: position.maxHeight,
        top: position.top,
        bottom: position.bottom,
      }
    : undefined

  return (
    <div className={`min-w-0 ${className}`}>
      <button
        ref={triggerRef}
        type="button"
        role="combobox"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listboxId}
        aria-activedescendant={open ? `${listboxId}-option-${activeIndex}` : undefined}
        aria-label={label}
        aria-invalid={invalid || undefined}
        title={selected.label}
        className={`flex min-h-11 w-full min-w-0 items-center justify-between gap-1 bg-transparent text-left text-xs leading-snug focus-visible:outline-none lg:min-h-0 ${invalid && !value ? 'text-warning' : 'text-ink'}`}
        onClick={() => open ? closeList() : openList()}
        onKeyDown={handleKeyDown}
      >
        {/* Sem truncate: o nome do acabamento aparece inteiro e quebra linha se
            não couber (o corte "Nogueira Natu…" foi justamente o defeito FRN-25). */}
        <span className="min-w-0 flex-1 break-words">{selected.label}</span>
        <ChevronDown className={`h-3.5 w-3.5 flex-shrink-0 text-muted transition-transform ${open ? 'rotate-180' : ''}`} aria-hidden="true" />
      </button>

      {open && position && createPortal(
        <ul
          ref={listRef}
          id={listboxId}
          role="listbox"
          aria-label={label}
          className="fixed z-dropdown overflow-y-auto rounded-xl border border-line bg-white py-1 shadow-xl"
          style={listStyle}
        >
          {allOptions.map((option, index) => (
            <li
              key={option.value || '__empty__'}
              id={`${listboxId}-option-${index}`}
              role="option"
              aria-selected={option.value === value}
              className={`flex min-h-11 cursor-pointer items-center gap-2.5 px-2.5 py-1.5 text-xs text-ink outline-none transition-colors ${index === activeIndex ? 'bg-surface-quiet' : 'hover:bg-bg-2'}`}
              onMouseEnter={() => setActiveIndex(index)}
              onMouseDown={event => event.preventDefault()}
              onClick={() => choose(option)}
            >
              {option.photoUrl
                ? <img src={option.photoUrl} alt="" loading="lazy" decoding="async" className="h-8 w-8 flex-shrink-0 rounded border border-line bg-white object-cover" />
                : <span aria-hidden="true" className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded border border-line bg-bg-2 text-[11px] font-semibold uppercase text-muted">
                    {option.label.trim().charAt(0) || '—'}
                  </span>}
              <span className="min-w-0 flex-1 break-words leading-snug">{option.label}</span>
            </li>
          ))}
        </ul>,
        document.body,
      )}
    </div>
  )
}
