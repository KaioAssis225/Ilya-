import { useCallback, useEffect, useState } from 'react'
import { LogOut, Pencil, ShieldCheck, X } from 'lucide-react'
import platformApi from '../lib/platformApi'
import { usePlatformAuth } from '../hooks/usePlatformAuth'
import type { PlatformCapability } from '../contexts/platformAuth'
import type { UserMarketAccess, UserRead, UserRole } from '../hooks/useUsers'

interface MarketRead {
  code: 'BR' | 'EU'
  name: string
  currency: string
  is_enabled: boolean
}

interface OutboxStatus {
  total: number
  counts: Record<string, number>
}

const ALL_CAPABILITIES: PlatformCapability[] = ['platform_admin', 'activate_market', 'read_outbox']
const ROLES: UserRole[] = ['admin', 'vendedor', 'representante', 'cadastros', 'produtos', 'cliente', 'executivo']

export default function PlatformPage() {
  const { user: platformUser, logout } = usePlatformAuth()
  const [markets, setMarkets] = useState<MarketRead[]>([])
  const [users, setUsers] = useState<UserRead[]>([])
  const [outbox, setOutbox] = useState<OutboxStatus | null>(null)
  const [editing, setEditing] = useState<UserRead | null>(null)
  const [capabilities, setCapabilities] = useState<PlatformCapability[]>([])
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    const marketResponse = await platformApi.get<MarketRead[]>('/markets')
    setMarkets(marketResponse.data)
    if (platformUser?.capabilities.includes('platform_admin')) {
      const userResponse = await platformApi.get<UserRead[]>('/users', { params: { limit: 200, include_total: false } })
      setUsers(userResponse.data)
    }
    if (platformUser?.capabilities.includes('read_outbox') || platformUser?.capabilities.includes('platform_admin')) {
      const response = await platformApi.get<OutboxStatus>('/integrations/outbox/status')
      setOutbox(response.data)
    }
  }, [platformUser])

  useEffect(() => {
    load().catch(() => setError('Não foi possível carregar os dados da plataforma.'))
  }, [load])

  async function toggleEurope(enabled: boolean) {
    setBusy(true)
    setError(null)
    try {
      await platformApi.post(`/markets/EU/${enabled ? 'activate' : 'deactivate'}`)
      await load()
    } catch (requestError: unknown) {
      const detail = (requestError as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(typeof detail === 'string' ? detail : 'Não foi possível alterar o mercado EU.')
    } finally {
      setBusy(false)
    }
  }

  async function openEditor(identity: UserRead) {
    setError(null)
    setNotice(null)
    try {
      const response = await platformApi.get<{ capabilities: PlatformCapability[] }>(`/users/${identity.id}/platform-permissions`)
      setCapabilities(response.data.capabilities)
      setEditing(structuredClone(identity))
    } catch {
      setError('Não foi possível carregar as permissões da identidade.')
    }
  }

  function updateAccess(code: 'BR' | 'EU', change: Partial<UserMarketAccess>) {
    if (!editing) return
    const accesses = editing.market_accesses.map(access => (
      access.market_code === code ? { ...access, ...change } : access
    ))
    setEditing({ ...editing, market_accesses: accesses, allowed_markets: accesses.map(access => access.market_code) })
  }

  function addAccess(code: 'BR' | 'EU') {
    if (!editing || editing.market_accesses.some(access => access.market_code === code)) return
    const access: UserMarketAccess = {
      market_code: code,
      role: 'vendedor',
      status: 'pending',
      linked_client_id: null,
      rep_id: null,
      can_view_dashboard: false,
      can_approve_tax: false,
    }
    setEditing({
      ...editing,
      market_accesses: [...editing.market_accesses, access],
      allowed_markets: [...editing.allowed_markets, code],
    })
  }

  async function saveMarketAccesses() {
    if (!editing) return
    const home = editing.market_accesses.find(access => access.market_code === editing.home_market)
    if (!home) {
      setError('O mercado principal precisa continuar associado à identidade.')
      return
    }
    setBusy(true)
    setError(null)
    setNotice(null)
    try {
      const response = await platformApi.patch<UserRead>(`/users/${editing.id}`, {
        email: editing.email,
        full_name: editing.full_name,
        is_active: editing.is_active,
        home_market: editing.home_market,
        role: home.role,
        rep_id: home.rep_id,
        can_view_dashboard: home.can_view_dashboard,
        market_accesses: editing.market_accesses,
      })
      setEditing(structuredClone(response.data))
      setNotice('Identidade e acessos comerciais salvos.')
      await load()
    } catch (requestError: unknown) {
      const detail = (requestError as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(typeof detail === 'string' ? detail : 'Não foi possível salvar a identidade.')
    } finally {
      setBusy(false)
    }
  }

  async function saveCapabilities() {
    if (!editing) return
    setBusy(true)
    setError(null)
    setNotice(null)
    try {
      await platformApi.put(`/users/${editing.id}/platform-permissions`, { capabilities })
      setNotice('Capacidades de plataforma salvas.')
      await load()
    } catch (requestError: unknown) {
      const detail = (requestError as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(typeof detail === 'string' ? detail : 'Não foi possível salvar as capacidades de plataforma.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="min-h-screen bg-bg p-5 md:p-8">
      <div className="mx-auto max-w-6xl space-y-6">
        <header className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <ShieldCheck className="h-7 w-7 text-gold" />
            <div><h1 className="text-2xl font-semibold text-ink">Plataforma Ilya</h1><p className="text-xs text-muted">{platformUser?.full_name}</p></div>
          </div>
          <button className="btn-secondary flex items-center gap-2" onClick={logout}><LogOut className="h-4 w-4" /> Sair</button>
        </header>

        {error && <p className="rounded-xl border border-terracotta/30 bg-white p-3 text-sm text-terracotta">{error}</p>}

        <section className="rounded-2xl border border-line bg-white p-5 shadow-sm">
          <h2 className="font-semibold text-ink">Mercados</h2>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            {markets.map(market => <div key={market.code} className="rounded-xl border border-line p-4"><div className="flex items-center justify-between"><div><strong>{market.name}</strong><p className="text-xs text-muted">{market.code} · {market.currency}</p></div><span className={market.is_enabled ? 'text-emerald-700' : 'text-muted'}>{market.is_enabled ? 'Ativo' : 'Desabilitado'}</span></div>{market.code === 'EU' && (platformUser?.capabilities.includes('activate_market') || platformUser?.capabilities.includes('platform_admin')) && <button disabled={busy} className="btn-secondary mt-3" onClick={() => toggleEurope(!market.is_enabled)}>{market.is_enabled ? 'Desabilitar EU' : 'Validar e ativar EU'}</button>}</div>)}
          </div>
        </section>

        {outbox && <section className="rounded-2xl border border-line bg-white p-5 shadow-sm"><h2 className="font-semibold text-ink">Outbox global</h2><p className="mt-2 text-sm text-muted">Total: {outbox.total} · {Object.entries(outbox.counts).map(([state, count]) => `${state}: ${count}`).join(' · ')}</p></section>}

        {platformUser?.capabilities.includes('platform_admin') && <section className="rounded-2xl border border-line bg-white shadow-sm overflow-hidden">
          <div className="p-5"><h2 className="font-semibold text-ink">Identidades e acessos</h2><p className="text-xs text-muted">Papéis e permissões são definidos separadamente em BR e EU.</p></div>
          <div className="overflow-x-auto"><table className="w-full text-sm"><thead className="bg-surface-alt"><tr><th className="px-5 py-3 text-left">Pessoa</th><th className="px-5 py-3 text-left">Mercados</th><th className="px-5 py-3 text-left">Estado</th><th className="px-5 py-3"></th></tr></thead><tbody>{users.map(identity => <tr key={identity.id} className="border-t border-line"><td className="px-5 py-3"><strong>{identity.full_name}</strong><p className="text-xs text-muted">{identity.email}</p></td><td className="px-5 py-3">{identity.market_accesses.map(access => `${access.market_code}: ${access.role} (${access.status})`).join(' · ') || 'Sem vínculo'}</td><td className="px-5 py-3">{identity.is_active ? 'Ativa' : 'Suspensa'}</td><td className="px-5 py-3 text-right"><button className="min-h-11 px-3 text-gold" onClick={() => openEditor(identity)}><Pencil className="h-4 w-4" /></button></td></tr>)}</tbody></table></div>
        </section>}
      </div>

      {editing && <div className="fixed inset-0 z-50 overflow-y-auto bg-scrim/60 p-4"><div className="mx-auto my-6 max-w-2xl rounded-2xl bg-white p-6 shadow-2xl"><div className="flex items-center justify-between"><h2 className="text-lg font-semibold">Editar identidade</h2><button onClick={() => setEditing(null)}><X /></button></div>{notice && <p className="mt-4 rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">{notice}</p>}<div className="mt-5 grid gap-4 sm:grid-cols-2"><label className="flex flex-col gap-1"><span className="text-xs text-muted">Nome</span><input className="input" value={editing.full_name} onChange={event => setEditing({ ...editing, full_name: event.target.value })} /></label><label className="flex flex-col gap-1"><span className="text-xs text-muted">E-mail</span><input className="input" value={editing.email} onChange={event => setEditing({ ...editing, email: event.target.value })} /></label><label className="flex flex-col gap-1"><span className="text-xs text-muted">Mercado principal</span><select className="input" value={editing.home_market} onChange={event => setEditing({ ...editing, home_market: event.target.value as 'BR' | 'EU' })}>{editing.market_accesses.map(access => <option key={access.market_code}>{access.market_code}</option>)}</select></label><label className="flex items-center gap-2 pt-5"><input type="checkbox" checked={editing.is_active} onChange={event => setEditing({ ...editing, is_active: event.target.checked })} /> Identidade ativa</label></div>
        <div className="mt-5 space-y-4">{editing.market_accesses.map(access => <fieldset key={access.market_code} className="rounded-xl border border-line p-4"><legend className="px-1 font-semibold">{access.market_code}</legend><div className="grid gap-3 sm:grid-cols-3"><label className="flex flex-col gap-1"><span className="text-xs text-muted">Papel</span><select className="input" value={access.role} onChange={event => updateAccess(access.market_code, { role: event.target.value as UserRole, linked_client_id: null, rep_id: null })}>{ROLES.map(role => <option key={role}>{role}</option>)}</select></label><label className="flex flex-col gap-1"><span className="text-xs text-muted">Estado</span><select className="input" value={access.status} onChange={event => updateAccess(access.market_code, { status: event.target.value as UserMarketAccess['status'] })}><option>pending</option><option>active</option><option>suspended</option></select></label>{access.role === 'cliente' && <label className="flex flex-col gap-1"><span className="text-xs text-muted">UUID do cliente</span><input className="input" value={access.linked_client_id ?? ''} onChange={event => updateAccess(access.market_code, { linked_client_id: event.target.value || null })} /></label>}{access.role === 'representante' && <label className="flex flex-col gap-1"><span className="text-xs text-muted">UUID do representante</span><input className="input" value={access.rep_id ?? ''} onChange={event => updateAccess(access.market_code, { rep_id: event.target.value || null })} /></label>}</div><div className="mt-3 flex flex-wrap gap-4"><label><input type="checkbox" checked={access.can_view_dashboard} onChange={event => updateAccess(access.market_code, { can_view_dashboard: event.target.checked })} /> Dashboard</label><label><input type="checkbox" checked={access.can_approve_tax} onChange={event => updateAccess(access.market_code, { can_approve_tax: event.target.checked })} /> Aprovar IVA</label></div>{access.market_code !== editing.home_market && <button className="mt-3 text-sm text-terracotta" onClick={() => setEditing({ ...editing, market_accesses: editing.market_accesses.filter(item => item.market_code !== access.market_code), allowed_markets: editing.allowed_markets.filter(item => item !== access.market_code) })}>Remover vínculo {access.market_code}</button>}</fieldset>)}{(['BR', 'EU'] as const).filter(code => !editing.market_accesses.some(access => access.market_code === code)).map(code => <button key={code} className="btn-secondary" onClick={() => addAccess(code)}>Adicionar {code}</button>)}</div>
        <div className="mt-5 flex justify-end"><button className="btn-primary" disabled={busy} onClick={saveMarketAccesses}>{busy ? 'Salvando…' : 'Salvar identidade e mercados'}</button></div>
        <fieldset className="mt-5 rounded-xl border border-line p-4"><legend className="px-1 font-semibold">Capacidades de plataforma</legend><div className="flex flex-wrap gap-4">{ALL_CAPABILITIES.map(capability => <label key={capability}><input type="checkbox" checked={capabilities.includes(capability)} onChange={event => setCapabilities(event.target.checked ? [...capabilities, capability] : capabilities.filter(item => item !== capability))} /> {capability}</label>)}</div><div className="mt-4 flex justify-end"><button className="btn-primary" disabled={busy} onClick={saveCapabilities}>{busy ? 'Salvando…' : 'Salvar capacidades'}</button></div></fieldset>
        <div className="mt-6 flex justify-end"><button className="btn-secondary" onClick={() => setEditing(null)}>Fechar</button></div></div></div>}
    </main>
  )
}
