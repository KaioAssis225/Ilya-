import assert from 'node:assert/strict'
import test from 'node:test'

import { shouldCloseModal } from './modalDismissal.ts'

test('formulário protegido fecha somente pelo botão X', () => {
  assert.equal(shouldCloseModal('backdrop', true), false)
  assert.equal(shouldCloseModal('escape', true), false)
  assert.equal(shouldCloseModal('close-button', true), true)
})

test('modal comum mantém o comportamento existente', () => {
  assert.equal(shouldCloseModal('backdrop', false), true)
  assert.equal(shouldCloseModal('escape', false), true)
  assert.equal(shouldCloseModal('close-button', false), true)
})
