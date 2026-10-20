// @vitest-environment jsdom

import { useState } from 'react'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it } from 'vitest'

import { OptionalApplicationGroup } from './OptionalApplicationGroup'
import type { OptionalApplicationInput, OptionalColor } from '../types'

afterEach(cleanup)

const category = { id: 'paint', code: 'PINTURA', name: 'Pintura' }
const optionals: OptionalColor[] = [
  { id: 'taupe', category: 'PINTURA', color_name: 'Taupe', photo_url: null },
]

function ApplicationEditor() {
  const [applications, setApplications] = useState<OptionalApplicationInput[]>([
    {
      category_id: category.id,
      name: 'Pés',
      name_en: 'Legs',
      required: true,
      display_order: 0,
      allow_all: false,
      allow_repeat: true,
      allowed_optional_ids: ['taupe'],
    },
  ])

  return (
    <OptionalApplicationGroup
      category={category}
      optionals={optionals}
      applications={applications}
      onChange={setApplications}
      onFirstAdd={() => undefined}
      initialAllowedIds={['taupe']}
      initialAllowAll={false}
    />
  )
}

it('edita aplicações independentes da mesma categoria', async () => {
  const user = userEvent.setup()
  render(<ApplicationEditor />)

  await user.click(screen.getByRole('button', { name: 'Adicionar outra aplicação' }))

  const names = screen.getAllByPlaceholderText('Ex.: Pintura dos pés')
  expect(names).toHaveLength(2)
  await user.type(names[1], 'Encosto')

  expect((names[0] as HTMLInputElement).value).toBe('Pés')
  expect((names[1] as HTMLInputElement).value).toBe('Encosto')
  const required = screen.getAllByRole('checkbox', { name: 'Obrigatória' })
  expect((required[0] as HTMLInputElement).checked).toBe(true)
  expect((required[1] as HTMLInputElement).checked).toBe(false)
})
