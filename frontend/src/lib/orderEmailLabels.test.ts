import { describe, expect, it } from 'vitest'
import {
  emailErrorMessage, emailRolesLabel, emailStatusInfo, formatEmailFileSize, LIVE_EMAIL_STATUSES,
} from './orderEmailLabels'

describe('orderEmailLabels', () => {
  it('traduz os cinco estados principais em português e inglês sem confundir aceito com entregue', () => {
    const pt = ['pending', 'processing', 'accepted', 'delivered', 'failed'].map((s) => emailStatusInfo(s, false).label)
    const en = ['pending', 'processing', 'accepted', 'delivered', 'failed'].map((s) => emailStatusInfo(s, true).label)
    expect(pt).toEqual(['Pendente', 'Processando', 'Aceito pelo serviço', 'Entregue', 'Falhou'])
    expect(en).toEqual(['Pending', 'Processing', 'Accepted by the service', 'Delivered', 'Failed'])
    expect(emailStatusInfo('accepted', false).hint).toBe('Aguardando confirmação de entrega.')
    expect(emailStatusInfo('delivered', false).hint).toBeNull()
  })

  it('cobre os estados de revisão, bloqueio e modo de teste', () => {
    expect(emailStatusInfo('needs_review', false)).toMatchObject({ label: 'Requer revisão', tone: 'warning' })
    expect(emailStatusInfo('blocked', true).label).toBe('No valid email')
    expect(emailStatusInfo('skipped', false).label).toBe('Não enviado (modo de teste)')
  })

  it('só considera "vivos" os estados que ainda podem mudar', () => {
    expect([...LIVE_EMAIL_STATUSES].sort()).toEqual(['accepted', 'pending', 'processing'])
  })

  it('rotula os papéis do destinatário', () => {
    expect(emailRolesLabel([], false)).toBe('Teste')
    expect(emailRolesLabel([], true)).toBe('Test')
    expect(emailRolesLabel(['client'], false)).toBe('Cliente')
    expect(emailRolesLabel(['representative'], true)).toBe('Representative')
    expect(emailRolesLabel(['client', 'representative'], false)).toBe('Cliente e representante')
  })

  it('mapeia códigos de erro e cai num texto genérico para códigos desconhecidos', () => {
    expect(emailErrorMessage('bounced', false)).toBe('O endereço recusou a mensagem (e-mail devolvido).')
    expect(emailErrorMessage('qualquer_coisa', false)).toBe('Erro no envio.')
    expect(emailErrorMessage('qualquer_coisa', true)).toBe('Sending error.')
    expect(emailErrorMessage(null, false)).toBeNull()
  })

  it('formata o tamanho do arquivo', () => {
    expect(formatEmailFileSize(null, 'pt-BR')).toBeNull()
    expect(formatEmailFileSize(120 * 1024, 'pt-BR')).toBe('120 KB')
    expect(formatEmailFileSize(Math.round(2.5 * 1024 * 1024), 'en-GB')).toBe('2.5 MB')
  })
})
