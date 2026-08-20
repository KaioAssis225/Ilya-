import { type CSSProperties } from 'react'
import { MarketFlag, type MarketCode } from './MarketFlag'

const LABELS: Record<MarketCode, string> = { BR: 'Brasil', EU: 'Portugal' }
const TRACE_COLORS: Record<MarketCode, string[]> = {
  BR: ['#009c3b', '#ffdf00', '#002776'],
  EU: ['#046a38', '#ffcc29', '#c8102e'],
}

const SPIRAL_PATHS = [
  'M72 520 C78 430 123 370 202 350 C290 328 330 264 300 205 C270 146 177 136 123 186 C65 239 92 323 170 344 C246 364 309 320 303 257 C298 207 242 177 197 198 C160 215 150 257 177 284 C201 308 242 303 256 276 C268 253 252 227 225 225 C204 224 190 239 193 256 C196 269 209 276 220 270 C229 266 231 256 226 249 C222 244 216 244 211 248',
  'M210 520 C199 438 249 383 309 349 C372 314 378 239 332 184 C285 128 194 126 132 165 C65 207 66 294 123 337 C182 382 276 353 303 292 C326 240 294 184 239 177 C194 171 156 204 158 247 C160 285 195 309 229 299 C259 290 273 258 257 235 C243 215 215 211 198 226 C184 238 186 258 199 269 C211 278 228 273 232 260 C235 251 228 243 220 243 C215 243 212 245 211 248',
  'M348 520 C337 425 288 375 219 350 C133 319 90 258 113 199 C137 138 223 119 291 154 C362 191 372 275 322 326 C271 378 180 371 136 316 C98 269 116 207 169 181 C215 159 270 181 284 226 C297 266 269 303 232 306 C198 309 173 283 178 253 C182 228 206 214 229 224 C247 232 254 253 243 268 C234 281 216 282 207 271 C199 262 202 250 211 248',
]

export function MarketTransition({ market }: { market: MarketCode }) {
  return (
    <div
      className={`market-transition market-transition-${market.toLowerCase()}`}
      role="status"
      aria-live="polite"
      aria-label={`Abrindo ambiente ${LABELS[market]}`}
    >
      <div className="market-transition-sweep" aria-hidden="true" />
      <svg
        className="market-transition-traces"
        viewBox="0 0 420 520"
        preserveAspectRatio="xMidYMid meet"
        aria-hidden="true"
      >
        {SPIRAL_PATHS.map((path, index) => (
          <path
            key={path}
            d={path}
            pathLength="1"
            style={{ '--trace-color': TRACE_COLORS[market][index] } as CSSProperties}
          />
        ))}
      </svg>
      <div className="market-transition-content">
        <MarketFlag market={market} animated className="market-transition-flag" />
        <span className="market-transition-name">ILYA — {LABELS[market].toUpperCase()}</span>
      </div>
    </div>
  )
}
