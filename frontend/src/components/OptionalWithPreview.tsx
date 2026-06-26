import { useState } from 'react'

interface Props {
  label: string
  swatch: string | null
}

export function OptionalWithPreview({ label, swatch }: Props) {
  const [show, setShow] = useState(false)

  return (
    <span
      className="relative inline-flex items-center gap-1 cursor-help"
      onMouseEnter={() => setShow(true)}
      onMouseLeave={() => setShow(false)}
      onTouchStart={() => setShow(true)}
      onTouchEnd={() => setShow(false)}
    >
      {swatch && (
        <img
          src={swatch}
          alt={label}
          className="w-4 h-4 rounded object-cover border border-[#e8e0d6] flex-shrink-0"
        />
      )}
      <span className="border-b border-dotted border-[#8b6914] text-[#2c2420] text-xs leading-tight">
        {label}
      </span>
      {show && swatch && (
        <span className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 z-50 flex flex-col items-center bg-white shadow-xl rounded-lg p-2 border border-[#e8e0d6] pointer-events-none">
          <img
            src={swatch}
            alt={label}
            className="w-24 h-24 rounded-lg object-cover"
          />
          <span className="text-xs text-[#2c2420] mt-1.5 text-center font-medium whitespace-nowrap">
            {label}
          </span>
        </span>
      )}
    </span>
  )
}
