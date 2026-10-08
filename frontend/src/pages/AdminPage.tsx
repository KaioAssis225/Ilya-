import { useEffect, useState } from 'react'
import { ChevronLeft, ChevronRight, KeyRound, Pencil, Plus, Search, ShieldCheck, Trash2, UserCheck, UserX, X } from 'lucide-react'
import { useUsersPage, useCreateUser, useUpdateUser, useResetUserPassword, useDeleteUser } from '../hooks/useUsers'
import type { UserRead, UserCreate, UserUpdate } from '../hooks/useUsers'
import { useRepresentative, useRepresentativesPage } from '../hooks/useRepresentatives'
import RetentionGovernancePanel from '../components/RetentionGovernancePanel'
import IncidentRegistryPanel from '../components/IncidentRegistryPanel'
import { useDialog } from '../hooks/useDialog'
import { useAuth } from '../hooks/useAuth'
import { useQuery } from '@tanstack/react-query'
import api from '../lib/api'

const ROLE_LABEL: Record<string, string> = {
  admin: 'Administrador',
  vendedor: 'Vendedor',
  representante: 'Representante',
  cadastros: 'Cadastros',
  produtos: 'Produtos',
  cliente: 'Cliente',
  executivo: 'Executivo',
}

// Só tokens do design system — todos ≥ 4.5:1 sobre o próprio fundo do badge.
const ROLE_BADGE: Record<string, string> = {
  admin: 'bg-gold/10 text-gold',
  vendedor: 'bg-mineral/10 text-mineral',
  representante: 'bg-olive/10 text-olive',
  cadastros: 'bg-bg-2 text-ink-2',
  produtos: 'bg-terracotta/10 text-terracotta',
  cliente: 'bg-bg-2 text-muted',
  executivo: 'bg-surface-warm text-ink-3',
}

type ModalMode = 'create' | 'edit' | 'password' | 'delete'

const EMPTY_CREATE: UserCreate = {
  email: '', password: '', full_name: '', role: 'vendedor', rep_id: null,
  home_market: 'BR', allowed_markets: ['BR'],
}

const USERS_PER_PAGE = 25

function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delayMs)
    return () => window.clearTimeout(timer)
  }, [value, delayMs])
  return debounced
}

export default function AdminPage() {
  const { user: currentUser } = useAuth()
  const [marketTab, setMarketTab] = useState<'BR' | 'EU'>(currentUser?.active_market ?? 'BR')
  const [showPriceComparison, setShowPriceComparison] = useState(false)
  const priceComparison = useQuery<Record<string, Record<string, Record<string, string>>>>({
    queryKey: ['markets', 'price-comparison'],
    queryFn: () => api.get('/markets/price-comparison').then(response => response.data),
    enabled: showPriceComparison,
    staleTime: 60_000,
  })
  const [userPage, setUserPage] = useState(1)
  const [userQuery, setUserQuery] = useState('')
  const debouncedUserQuery = useDebouncedValue(userQuery.trim(), 300)
  const { data: usersPage, isLoading, isFetching } = useUsersPage({
    skip: (userPage - 1) * USERS_PER_PAGE,
    limit: USERS_PER_PAGE,
    q: debouncedUserQuery || undefined,
    sort_by: 'full_name',
    sort_dir: 'asc',
    market: marketTab,
  })
  const users = usersPage?.items ?? []
  const totalUsers = usersPage?.total ?? 0
  const totalUserPages = usersPage
    ? Math.max(1, Math.ceil(totalUsers / USERS_PER_PAGE))
    : Math.max(1, userPage)
  const createM = useCreateUser()
  const updateM = useUpdateUser()
  const resetPwM = useResetUserPassword()
  const deleteM = useDeleteUser()

  const [modal, setModal] = useState<{ mode: ModalMode; user?: UserRead } | null>(null)
  // Escape fecha, foco preso no painel e devolvido ao botão que abriu.
  const dialogRef = useDialog(() => setModal(null), modal !== null)
  const [form, setForm] = useState<UserCreate>(EMPTY_CREATE)
  const [editForm, setEditForm] = useState<UserUpdate>({})
  const [newPassword, setNewPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [toast, setToast] = useState<string | null>(null)
  const [repQuery, setRepQuery] = useState('')
  const debouncedRepQuery = useDebouncedValue(repQuery.trim(), 300)
  const repPickerOpen = (
    (modal?.mode === 'create' && form.role === 'representante')
    || (modal?.mode === 'edit' && editForm.role === 'representante')
  )
  const { data: repsPage, isFetching: repsLoading } = useRepresentativesPage({
    skip: 0,
    limit: 20,
    q: debouncedRepQuery || undefined,
    include_total: false,
    sort_by: 'name',
    sort_dir: 'asc',
  }, repPickerOpen)
  const selectedRepId = (
    modal?.mode === 'edit' ? editForm.rep_id : form.rep_id
  ) ?? ''
  const { data: selectedRep } = useRepresentative(
    selectedRepId,
    !!selectedRepId,
  )
  const reps = [
    ...(selectedRep ? [selectedRep] : []),
    ...(repsPage?.items ?? []).filter((rep) => rep.id !== selectedRep?.id),
  ]

  useEffect(() => {
    if (usersPage && userPage > totalUserPages) setUserPage(totalUserPages)
  }, [usersPage, totalUserPages, userPage])

  function showToast(msg: string) {
    setToast(msg)
    setTimeout(() => setToast(null), 3000)
  }

  function openCreate() {
    setForm({ ...EMPTY_CREATE, home_market: marketTab, allowed_markets: [marketTab] })
    setRepQuery('')
    setError(null)
    setModal({ mode: 'create' })
  }

  function openEdit(u: UserRead) {
    const homeAccess = u.market_accesses.find(access => access.market_code === u.home_market)
    setEditForm({ email: u.email, username: u.username ?? '', full_name: u.full_name, role: homeAccess?.role ?? u.role, rep_id: homeAccess?.rep_id ?? u.rep_id, is_active: u.is_active, can_view_dashboard: homeAccess?.can_view_dashboard ?? u.can_view_dashboard, home_market: u.home_market, allowed_markets: u.allowed_markets, market_accesses: u.market_accesses })
    setRepQuery('')
    setError(null)
    setModal({ mode: 'edit', user: u })
  }

  function openPassword(u: UserRead) {
    setNewPassword('')
    setError(null)
    setModal({ mode: 'password', user: u })
  }

  function openDelete(u: UserRead) {
    setModal({ mode: 'delete', user: u })
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    try {
      await createM.mutateAsync(form)
      setModal(null)
      showToast('Usuário criado com sucesso!')
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(msg ?? 'Erro ao criar usuário.')
    }
  }

  async function handleEdit(e: React.FormEvent) {
    e.preventDefault()
    if (!modal?.user) return
    setError(null)
    try {
      await updateM.mutateAsync({ id: modal.user.id, ...editForm })
      setModal(null)
      showToast('Usuário atualizado!')
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(msg ?? 'Erro ao atualizar.')
    }
  }

  async function handlePassword(e: React.FormEvent) {
    e.preventDefault()
    if (!modal?.user) return
    setError(null)
    try {
      await resetPwM.mutateAsync({ id: modal.user.id, new_password: newPassword })
      setModal(null)
      showToast('Senha redefinida com sucesso!')
    } catch {
      setError('Erro ao redefinir senha.')
    }
  }

  async function handleDelete() {
    if (!modal?.user) return
    try {
      await deleteM.mutateAsync(modal.user.id)
      setModal(null)
      showToast('Usuário excluído.')
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(msg ?? 'Erro ao excluir.')
    }
  }

  return (
    <div className="min-h-screen bg-bg">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 py-6 sm:py-8 pb-28 md:pb-8">
        <div className="flex items-center justify-between gap-3 mb-7">
          <div>
            <h1 className="font-display text-2xl font-semibold text-ink flex items-center gap-2">
              <ShieldCheck className="w-6 h-6 text-gold" /> Gerenciar Usuários
            </h1>
            <p className="text-sm text-muted mt-1">Área exclusiva do Administrador</p>
          </div>
          <button
            type="button"
            onClick={openCreate}
            className="btn-primary shrink-0"
          >
            <Plus className="w-4 h-4" /> Novo Usuário
          </button>
        </div>
        <section className="bg-white border border-line rounded-2xl shadow-sm overflow-hidden">
          <div className="flex items-center justify-between gap-4 px-5 py-4">
            <div className="min-w-0"><h2 className="text-sm font-semibold text-ink">Comparação de preços por mercado</h2><p className="mt-1 text-xs text-muted">Área administrativa; valores de Brasil e Europa não aparecem nas telas operacionais ao mesmo tempo.</p></div>
            <button type="button" className="btn-secondary shrink-0" onClick={() => setShowPriceComparison(value => !value)}>{showPriceComparison ? 'Ocultar' : 'Comparar'}</button>
          </div>
          {showPriceComparison && <div className="max-h-96 overflow-auto border-t border-line">
            {priceComparison.isLoading ? <p className="p-5 text-sm text-muted">Carregando preços…</p> : priceComparison.isError ? <p role="alert" className="p-5 text-sm font-medium text-danger">Não foi possível carregar a comparação. Tente novamente.</p> : <table className="w-full min-w-[680px] text-sm"><thead className="sticky top-0 bg-surface-2"><tr><th className="px-5 py-3 text-left">SKU</th><th className="px-5 py-3 text-left">Brasil</th><th className="px-5 py-3 text-left">Europa</th></tr></thead><tbody>{Object.entries(priceComparison.data ?? {}).map(([sku, markets]) => <tr key={sku} className="border-t border-line"><td className="px-5 py-3 font-mono font-medium text-gold">{sku}</td><td className="px-5 py-3 text-ink-2">{Object.entries(markets.BR ?? {}).map(([list, value]) => `${list}: ${value}`).join(' · ') || '—'}</td><td className="px-5 py-3 text-ink-2">{Object.entries(markets.EU ?? {}).map(([list, value]) => `${list}: ${value}`).join(' · ') || '—'}</td></tr>)}</tbody></table>}
          </div>}
        </section>

        <div className="bg-white border border-line rounded-2xl shadow-sm overflow-hidden">
          <div className="flex gap-1 border-b border-line bg-surface-2 px-5 pt-3" role="tablist" aria-label="Usuários por mercado">
            {(['BR', 'EU'] as const).map(code => (
              <button
                key={code}
                type="button"
                role="tab"
                aria-selected={marketTab === code}
                onClick={() => { setMarketTab(code); setUserPage(1) }}
                className={`min-h-11 px-4 text-xs font-semibold uppercase tracking-wide border-b-2 transition-colors ${marketTab === code ? 'border-gold text-gold' : 'border-transparent text-muted hover:text-ink'}`}
              >
                {code === 'BR' ? 'Brasil' : 'Europa'}
              </button>
            ))}
          </div>
          <div className="flex flex-col gap-3 border-b border-line px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="relative w-full sm:max-w-sm">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
              <input
                aria-label="Buscar usuários por nome, e-mail ou usuário"
                type="search"
                value={userQuery}
                onChange={(event) => {
                  setUserQuery(event.target.value)
                  setUserPage(1)
                }}
                placeholder="Buscar por nome, e-mail ou usuário"
                className="input w-full pl-9"
              />
            </div>
            <span className="text-xs text-muted">
              {isFetching && !isLoading ? 'Atualizando…' : `${totalUsers} usuário(s)`}
            </span>
          </div>
          {/* O card pai tem overflow-hidden: sem este wrapper Perfil/Status/Ações
              ficavam cortados fora da tela no celular. */}
          <div className="w-full overflow-x-auto overscroll-x-contain">
          <table className="w-full min-w-[560px] text-sm">
            <thead className="bg-surface-2">
              <tr>
                <th className="px-5 py-3 text-left text-xs font-semibold text-muted uppercase tracking-wider">Nome</th>
                <th className="px-5 py-3 text-left text-xs font-semibold text-muted uppercase tracking-wider">E-mail</th>
                <th className="px-5 py-3 text-left text-xs font-semibold text-muted uppercase tracking-wider">Perfil</th>
                <th className="px-5 py-3 text-left text-xs font-semibold text-muted uppercase tracking-wider">Status</th>
                <th className="px-5 py-3"></th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                <tr><td colSpan={5} className="text-center py-10 text-muted">Carregando…</td></tr>
              ) : users.length === 0 ? (
                <tr><td colSpan={5} className="text-center py-10 text-muted">Nenhum usuário encontrado.</td></tr>
              ) : users.map(u => (
                <tr key={u.id} className="border-t border-line hover:bg-surface-quiet transition-colors">
                  <td className="px-5 py-3 font-medium text-ink">{u.full_name}</td>
                  <td className="px-5 py-3 text-ink-2">{u.email}</td>
                  <td className="px-5 py-3">
                    <span className={`text-xs font-semibold px-2.5 py-1 rounded-full whitespace-nowrap ${ROLE_BADGE[u.role] ?? 'bg-bg-2 text-muted'}`}>
                      {ROLE_LABEL[u.role]}
                    </span>
                  </td>
                  <td className="px-5 py-3">
                    {u.is_active
                      ? <span className="flex items-center gap-1 text-xs text-olive"><UserCheck className="w-3.5 h-3.5" /> Ativo</span>
                      : <span className="flex items-center gap-1 text-xs text-terracotta"><UserX className="w-3.5 h-3.5" /> Inativo</span>
                    }
                  </td>
                  <td className="px-5 py-3">
                    <div className="flex items-center gap-1 justify-end">
                      <button type="button" onClick={() => openEdit(u)} title="Editar" aria-label={`Editar ${u.full_name}`} className="btn-icon"><Pencil className="w-4 h-4" /></button>
                      <button type="button" onClick={() => openPassword(u)} title="Redefinir Senha" aria-label={`Redefinir senha de ${u.full_name}`} className="btn-icon hover:text-mineral"><KeyRound className="w-4 h-4" /></button>
                      <button type="button" onClick={() => openDelete(u)} title="Excluir" aria-label={`Excluir ${u.full_name}`} className="btn-icon hover:text-danger"><Trash2 className="w-4 h-4" /></button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
          <div className="flex items-center justify-between border-t border-line px-5 py-3">
            <span className="text-xs text-muted">
              Página {userPage} de {totalUserPages}
            </span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                aria-label="Página anterior"
                disabled={userPage <= 1 || isFetching}
                onClick={() => setUserPage((page) => Math.max(1, page - 1))}
                className="btn-secondary flex h-11 w-11 lg:h-9 lg:w-9 items-center justify-center p-0 disabled:opacity-40"
              >
                <ChevronLeft className="h-4 w-4" />
              </button>
              <button
                type="button"
                aria-label="Próxima página"
                disabled={userPage >= totalUserPages || isFetching}
                onClick={() => setUserPage((page) => Math.min(totalUserPages, page + 1))}
                className="btn-secondary flex h-11 w-11 lg:h-9 lg:w-9 items-center justify-center p-0 disabled:opacity-40"
              >
                <ChevronRight className="h-4 w-4" />
              </button>
            </div>
          </div>
        </div>
        <RetentionGovernancePanel />
        <IncidentRegistryPanel />
      </div>

      {/* Modais */}
      {modal && (
        <div className="modal-overlay z-modal items-center" onClick={e => { if (e.target === e.currentTarget) setModal(null) }}>
          <div ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby="admin-modal-title" tabIndex={-1} className="modal-panel w-full max-w-md p-6 my-auto">

            {/* CRIAR */}
            {modal.mode === 'create' && (
              <form onSubmit={handleCreate} className="space-y-4">
                <div className="flex items-center justify-between mb-1">
                  <h3 id="admin-modal-title" className="text-base font-semibold text-ink">Novo Usuário</h3>
                  <button type="button" onClick={() => setModal(null)} aria-label="Fechar" className="btn-icon -mr-2"><X className="w-5 h-5" /></button>
                </div>
                <label className="flex flex-col gap-1">
                  <span className="text-xs text-muted">Nome Completo *</span>
                  <input className="input" value={form.full_name} onChange={e => setForm({ ...form, full_name: e.target.value })} required />
                </label>
                <fieldset className="space-y-2 rounded-xl border border-line p-3">
                  <legend className="px-1 text-xs font-semibold uppercase tracking-wide text-muted">Acesso a mercados</legend>
                  <div className="flex gap-4">
                    {(['BR', 'EU'] as const).map(code => (
                      <label key={code} className="flex min-h-11 items-center gap-2 text-sm text-ink">
                        <input type="checkbox" className="h-4 w-4 accent-gold" checked={form.allowed_markets.includes(code)} disabled={code === form.home_market} onChange={event => {
                          const allowed = event.target.checked ? [...form.allowed_markets, code] : form.allowed_markets.filter(item => item !== code)
                          setForm({ ...form, allowed_markets: allowed.length ? allowed : [form.home_market] })
                        }} />
                        {code === 'BR' ? 'Brasil' : 'Europa'}
                      </label>
                    ))}
                  </div>
                  <label className="flex flex-col gap-1">
                    <span className="text-xs text-muted">Mercado principal</span>
                    <select className="input" value={form.home_market} onChange={event => {
                      const home = event.target.value as 'BR' | 'EU'
                      setForm({ ...form, home_market: home, allowed_markets: Array.from(new Set([...form.allowed_markets, home])) })
                    }}>
                      <option value="BR">Brasil</option><option value="EU">Europa</option>
                    </select>
                  </label>
                </fieldset>
                <label className="flex flex-col gap-1">
                  <span className="text-xs text-muted">E-mail *</span>
                  <input className="input" type="email" value={form.email} onChange={e => setForm({ ...form, email: e.target.value })} required />
                </label>
                <label className="flex flex-col gap-1">
                  <span className="text-xs text-muted">Senha *</span>
                  <input className="input" type="password" value={form.password} onChange={e => setForm({ ...form, password: e.target.value })} required minLength={8} />
                </label>
                <label className="flex flex-col gap-1">
                  <span className="text-xs text-muted">Perfil *</span>
                  <select className="input" value={form.role} onChange={e => {
                    const role = e.target.value as UserCreate['role']
                    setForm({ ...form, role, rep_id: role === 'representante' ? form.rep_id : null })
                  }}>
                    <option value="vendedor">Vendedor</option>
                    <option value="representante">Representante</option>
                    <option value="cadastros">Cadastros</option>
                    <option value="produtos">Produtos</option>
                    <option value="executivo">Executivo</option>
                    <option value="admin">Administrador</option>
                  </select>
                </label>
                {form.role === 'representante' && (
                  <label className="flex flex-col gap-1">
                    <span className="text-xs text-muted">Representante vinculado</span>
                    <input
                      className="input"
                      placeholder="Buscar representante..."
                      value={repQuery}
                      onChange={e => setRepQuery(e.target.value)}
                    />
                    <select className="input" value={form.rep_id ?? ''} onChange={e => setForm({ ...form, rep_id: e.target.value || null })}>
                      <option value="">— Nenhum —</option>
                      {reps.map(r => <option key={r.id} value={r.id}>{r.name}</option>)}
                    </select>
                    {repsLoading && <span className="text-[11px] text-muted">Buscando…</span>}
                  </label>
                )}
                {error && <p className="text-xs text-terracotta">{error}</p>}
                <div className="flex gap-2 pt-1">
                  <button type="button" onClick={() => setModal(null)} className="flex-1 py-2 border border-line text-muted rounded-lg text-sm hover:bg-bg transition-colors">Cancelar</button>
                  <button type="submit" disabled={createM.isPending} className="btn-primary flex-1">
                    {createM.isPending ? 'Criando…' : 'Criar Usuário'}
                  </button>
                </div>
              </form>
            )}

            {/* EDITAR */}
            {modal.mode === 'edit' && modal.user && (
              <form onSubmit={handleEdit} className="space-y-4">
                <div className="flex items-center justify-between mb-1">
                  <h3 id="admin-modal-title" className="text-base font-semibold text-ink">Editar Usuário</h3>
                  <button type="button" onClick={() => setModal(null)} aria-label="Fechar" className="btn-icon -mr-2"><X className="w-5 h-5" /></button>
                </div>
                <label className="flex flex-col gap-1">
                  <span className="text-xs text-muted">Nome Completo</span>
                  <input className="input" value={editForm.full_name ?? ''} onChange={e => setEditForm({ ...editForm, full_name: e.target.value })} />
                </label>
                <label className="flex flex-col gap-1">
                  <span className="text-xs text-muted">E-mail</span>
                  <input className="input" type="email" value={editForm.email ?? ''} onChange={e => setEditForm({ ...editForm, email: e.target.value })} />
                </label>
                <label className="flex flex-col gap-1">
                  <span className="text-xs text-muted">Login</span>
                  <input
                    className="input"
                    value={editForm.username ?? ''}
                    onChange={e => setEditForm({ ...editForm, username: e.target.value })}
                    minLength={3}
                    maxLength={100}
                    pattern="[A-Za-z0-9._-]+"
                    autoCapitalize="none"
                    autoCorrect="off"
                    required
                  />
                </label>
                <label className="flex flex-col gap-1">
                  <span className="text-xs text-muted">Perfil no mercado principal</span>
                  <select className="input" value={editForm.role ?? 'vendedor'} onChange={e => {
                    const role = e.target.value as UserUpdate['role']
                    setEditForm({ ...editForm, role, rep_id: role === 'representante' ? editForm.rep_id : null })
                  }}>
                    <option value="vendedor">Vendedor</option>
                    <option value="representante">Representante</option>
                    <option value="cadastros">Cadastros</option>
                    <option value="produtos">Produtos</option>
                    <option value="executivo">Executivo</option>
                    <option value="admin">Administrador</option>
                  </select>
                </label>
                {editForm.role === 'representante' && (
                  <label className="flex flex-col gap-1">
                    <span className="text-xs text-muted">Representante vinculado</span>
                    <input
                      className="input"
                      placeholder="Buscar representante..."
                      value={repQuery}
                      onChange={e => setRepQuery(e.target.value)}
                    />
                    <select className="input" value={editForm.rep_id ?? ''} onChange={e => setEditForm({ ...editForm, rep_id: e.target.value || null })}>
                      <option value="">— Nenhum —</option>
                      {reps.map(r => <option key={r.id} value={r.id}>{r.name}</option>)}
                    </select>
                    {repsLoading && <span className="text-[11px] text-muted">Buscando…</span>}
                  </label>
                )}
                <fieldset className="space-y-2 rounded-xl border border-line p-3">
                  <legend className="px-1 text-xs font-semibold uppercase tracking-wide text-muted">Acesso a mercados</legend>
                  <div className="flex gap-4">
                    {(['BR', 'EU'] as const).map(code => (
                      <label key={code} className="flex min-h-11 items-center gap-2 text-sm text-ink">
                        <input type="checkbox" className="h-4 w-4 accent-gold" checked={(editForm.allowed_markets ?? []).includes(code)} disabled={code === editForm.home_market} onChange={event => {
                          const current = editForm.allowed_markets ?? []
                          const allowed = event.target.checked ? [...current, code] : current.filter(item => item !== code)
                          setEditForm({ ...editForm, allowed_markets: allowed })
                        }} />
                        {code === 'BR' ? 'Brasil' : 'Europa'}
                      </label>
                    ))}
                  </div>
                  <label className="flex flex-col gap-1">
                    <span className="text-xs text-muted">Mercado principal</span>
                    <select className="input" value={editForm.home_market ?? 'BR'} onChange={event => {
                      const home = event.target.value as 'BR' | 'EU'
                      const access = editForm.market_accesses?.find(item => item.market_code === home)
                      setEditForm({
                        ...editForm,
                        home_market: home,
                        allowed_markets: Array.from(new Set([...(editForm.allowed_markets ?? []), home])),
                        role: access?.role ?? 'vendedor',
                        rep_id: access?.rep_id ?? null,
                        can_view_dashboard: access?.can_view_dashboard ?? false,
                      })
                    }}><option value="BR">Brasil</option><option value="EU">Europa</option></select>
                  </label>
                </fieldset>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input type="checkbox" checked={editForm.is_active ?? true} onChange={e => setEditForm({ ...editForm, is_active: e.target.checked })} className="w-4 h-4 accent-gold" />
                  <span className="text-sm text-ink-2">Usuário ativo</span>
                </label>
                {editForm.role !== 'executivo' && (
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input type="checkbox" checked={editForm.can_view_dashboard ?? false} onChange={e => setEditForm({ ...editForm, can_view_dashboard: e.target.checked })} className="w-4 h-4 accent-gold" />
                    <span className="text-sm text-ink-2">Pode ver o Dashboard BI</span>
                  </label>
                )}
                {error && <p className="text-xs text-terracotta">{error}</p>}
                <div className="flex gap-2 pt-1">
                  <button type="button" onClick={() => setModal(null)} className="flex-1 py-2 border border-line text-muted rounded-lg text-sm hover:bg-bg transition-colors">Cancelar</button>
                  <button type="submit" disabled={updateM.isPending} className="btn-primary flex-1">
                    {updateM.isPending ? 'Salvando…' : 'Salvar'}
                  </button>
                </div>
              </form>
            )}

            {/* REDEFINIR SENHA */}
            {modal.mode === 'password' && modal.user && (
              <form onSubmit={handlePassword} className="space-y-4">
                <div className="flex items-center justify-between mb-1">
                  <h3 id="admin-modal-title" className="text-base font-semibold text-ink">Redefinir Senha</h3>
                  <button type="button" onClick={() => setModal(null)} aria-label="Fechar" className="btn-icon -mr-2"><X className="w-5 h-5" /></button>
                </div>
                <p className="text-sm text-ink-2">Usuário: <strong>{modal.user.full_name}</strong></p>
                <label className="flex flex-col gap-1">
                  <span className="text-xs text-muted">Nova Senha *</span>
                  <input className="input" type="password" value={newPassword} onChange={e => setNewPassword(e.target.value)} required minLength={8} />
                </label>
                {error && <p className="text-xs text-terracotta">{error}</p>}
                <div className="flex gap-2 pt-1">
                  <button type="button" onClick={() => setModal(null)} className="flex-1 py-2 border border-line text-muted rounded-lg text-sm hover:bg-bg transition-colors">Cancelar</button>
                  <button type="submit" disabled={resetPwM.isPending} className="flex-1 py-2 bg-mineral text-white rounded-lg text-sm font-medium hover:bg-mineral-700 transition-colors disabled:opacity-60">
                    {resetPwM.isPending ? 'Redefinindo…' : 'Redefinir Senha'}
                  </button>
                </div>
              </form>
            )}

            {/* EXCLUIR */}
            {modal.mode === 'delete' && modal.user && (
              <div className="space-y-4">
                <div className="flex items-center justify-between mb-1">
                  <h3 id="admin-modal-title" className="text-base font-semibold text-ink">Excluir Usuário</h3>
                  <button type="button" onClick={() => setModal(null)} aria-label="Fechar" className="btn-icon -mr-2"><X className="w-5 h-5" /></button>
                </div>
                <p className="text-sm text-ink-2">Tem certeza que deseja excluir <strong>{modal.user.full_name}</strong>? Esta ação não pode ser desfeita.</p>
                {error && <p className="text-xs text-terracotta">{error}</p>}
                <div className="flex gap-2 pt-1">
                  <button onClick={() => setModal(null)} className="flex-1 py-2 border border-line text-muted rounded-lg text-sm hover:bg-bg transition-colors">Cancelar</button>
                  <button onClick={handleDelete} disabled={deleteM.isPending} className="flex-1 py-2 bg-danger text-white rounded-lg text-sm font-medium hover:bg-terracotta-700 transition-colors disabled:opacity-60">
                    {deleteM.isPending ? 'Excluindo…' : 'Excluir'}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {toast && (
        <div role="status" aria-live="polite" className="fixed bottom-6 right-6 bg-ink text-white text-sm px-4 py-3 rounded-xl shadow-lg z-50">
          {toast}
        </div>
      )}
    </div>
  )
}
