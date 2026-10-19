import '@testing-library/jest-dom/vitest'
import * as matchers from '@testing-library/jest-dom/matchers'
import { cleanup } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, expect } from 'vitest'
import { setupServer } from 'msw/node'

export const server = setupServer()
expect.extend(matchers)

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))

if (!window.matchMedia) {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: (query: string): MediaQueryList => {
      const listeners = new Set<EventListenerOrEventListenerObject>()
      const mediaQuery: MediaQueryList = {
        matches: false,
        media: query,
        onchange: null,
        addListener(listener) { if (listener) listeners.add(listener as EventListener) },
        removeListener(listener) { if (listener) listeners.delete(listener as EventListener) },
        addEventListener(_type: string, listener: EventListenerOrEventListenerObject | null) { if (listener) listeners.add(listener) },
        removeEventListener(_type: string, listener: EventListenerOrEventListenerObject | null) { if (listener) listeners.delete(listener) },
        dispatchEvent(event) {
          listeners.forEach(listener => {
            if (typeof listener === 'function') listener.call(mediaQuery, event)
            else listener.handleEvent(event)
          })
          mediaQuery.onchange?.call(mediaQuery, event as MediaQueryListEvent)
          return !event.defaultPrevented
        },
      }
      return mediaQuery
    },
  })
}

afterEach(() => {
  cleanup()
  server.resetHandlers()
  localStorage.clear()
  sessionStorage.clear()
})

afterAll(() => server.close())
