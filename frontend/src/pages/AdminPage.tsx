import { useState } from 'react'
import { Plus, Pencil, Trash2, KeyRound, X, ShieldCheck, UserCheck, UserX } from 'lucide-react'
import { useUsers, useCreateUser, useUpdateUser, useResetUserPassword, useDeleteUser } from '../hooks/useUsers'
import type { UserRead, UserCreate, UserUpdate } from '../hooks/useUsers'
import { useRepresentatives } from '../hooks/useRepresentatives'

const ROLE_LABEL: Record<string, string> = {
  admin: 'Administrador',
  vendedor: 'Vendedor',
  representante: 'Representante',
  cadastros: 'Cadastros',
  produtos: 'Produtos',
  cliente: 'Cliente',
  executivo: 'Executivo',
}

const ROLE_COLOR: Record<string, string> = {
  admin: '#8b6914',
  vendedor: '#507a9b',
  representante: '#648261',
  cadastros: '#7a5a9b',
  produtos: '#9b5a50',
  cliente: '#a08558',
  executivo: '#5a7a8b',
}

type ModalMode = 'create' | 'edit' | 'password' | 'delete'

const EMPTY_CREATE: UserCreate = {
  email: '', password: '', full_name: '', role: 'vendedor', rep_id: null,
}

export default function AdminPage() {
  const { data: users = [], isLoading } = useUsers()
  const { data: reps = [] } = useRepresentatives()
  const createM = useCreateUser()
  const updateM = useUpdateUser()
  const resetPwM = useResetUserPassword()
  const deleteM = useDeleteUser()

  const [modal, setModal] = useState<{ mode: ModalMode; user?: UserRead } | null>(null)
  const [form, setForm] = useState<UserCreate>(EMPTY_CREATE)
  const [editForm, setEditForm] = useState<UserUpdate>({})
  const [newPassword, setNewPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [toast, setToast] = useState<string | null>(null)

  function showToast(msg: string) {
    setToast(msg)
    setTimeout(() => setToast(null), 3000)
  }

  function openCreate() {
    setForm(EMPTY_CREATE)
    setError(null)
    setModal({ mode: 'create' })
  }

  function openEdit(u: UserRead) {
    setEditForm({ email: u.email, full_name: u.full_name, role: u.role, rep_id: u.rep_id, is_active: u.is_active, can_view_dashboard: u.can_view_dashboard })
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
      <div className="max-w-4xl mx-auto px-6 py-8">
        <div className="flex items-center justify-between mb-7">
          <div>
            <h2 className="text-2xl font-semibold text-ink flex items-center gap-2" style={{ fontFamily: 'Cormorant Garamond, Georgia, serif' }}>
              <ShieldCheck className="w-6 h-6 text-gold" /> Gerenciar Usuários
            </h2>
            <p className="text-sm text-muted mt-1">Área exclusiva do Administrador</p>
          </div>
          <button
            onClick={openCreate}
            className="flex items-center gap-2 px-4 py-2 bg-gold text-white rounded-xl text-sm font-medium hover:bg-gold-600 transition-colors shadow-sm"
          >
            <Plus className="w-4 h-4" /> Novo Usuário
          </button>
        </div>

        <div className="bg-white border border-line rounded-2xl shadow-sm overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-bg-2">
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
              ) : users.map(u => (
                <tr key={u.id} className="border-t border-line hover:bg-[#fdfcfa] transition-colors">
                  <td className="px-5 py-3 font-medium text-ink">{u.full_name}</td>
                  <td className="px-5 py-3 text-ink-2">{u.email}</td>
                  <td className="px-5 py-3">
                    <span className="text-xs font-semibold px-2.5 py-1 rounded-full" style={{ backgroundColor: `${ROLE_COLOR[u.role]}18`, color: ROLE_COLOR[u.role] }}>
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
                    <div className="flex items-center gap-2 justify-end">
                      <button onClick={() => openEdit(u)} title="Editar" aria-label="Editar" className="text-muted hover:text-gold transition-colors"><Pencil className="w-4 h-4" /></button>
                      <button onClick={() => openPassword(u)} title="Redefinir Senha" className="text-muted hover:text-mineral transition-colors"><KeyRound className="w-4 h-4" /></button>
                      <button onClick={() => openDelete(u)} title="Excluir" className="text-muted hover:text-terracotta transition-colors"><Trash2 className="w-4 h-4" /></button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Modais */}
      {modal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-scrim/60 backdrop-blur-sm">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md mx-4 p-6" onClick={e => e.stopPropagation()}>

            {/* CRIAR */}
            {modal.mode === 'create' && (
              <form onSubmit={handleCreate} className="space-y-4">
                <div className="flex items-center justify-between mb-1">
                  <h3 className="text-base font-semibold text-ink">Novo Usuário</h3>
                  <button type="button" onClick={() => setModal(null)} className="text-muted hover:text-ink"><X className="w-5 h-5" /></button>
                </div>
                <label className="flex flex-col gap-1">
                  <span className="text-xs text-muted">Nome Completo *</span>
                  <input className="input" value={form.full_name} onChange={e => setForm({ ...form, full_name: e.target.value })} required />
                </label>
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
                  <select className="input" value={form.role} onChange={e => setForm({ ...form, role: e.target.value as UserCreate['role'] })}>
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
                    <select className="input" value={form.rep_id ?? ''} onChange={e => setForm({ ...form, rep_id: e.target.value || null })}>
                      <option value="">— Nenhum —</option>
                      {reps.map(r => <option key={r.id} value={r.id}>{r.name}</option>)}
                    </select>
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
                  <h3 className="text-base font-semibold text-ink">Editar Usuário</h3>
                  <button type="button" onClick={() => setModal(null)} className="text-muted hover:text-ink"><X className="w-5 h-5" /></button>
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
                  <span className="text-xs text-muted">Perfil</span>
                  <select className="input" value={editForm.role ?? 'vendedor'} onChange={e => setEditForm({ ...editForm, role: e.target.value as UserUpdate['role'] })}>
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
                    <select className="input" value={editForm.rep_id ?? ''} onChange={e => setEditForm({ ...editForm, rep_id: e.target.value || null })}>
                      <option value="">— Nenhum —</option>
                      {reps.map(r => <option key={r.id} value={r.id}>{r.name}</option>)}
                    </select>
                  </label>
                )}
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
                  <h3 className="text-base font-semibold text-ink">Redefinir Senha</h3>
                  <button type="button" onClick={() => setModal(null)} className="text-muted hover:text-ink"><X className="w-5 h-5" /></button>
                </div>
                <p className="text-sm text-ink-2">Usuário: <strong>{modal.user.full_name}</strong></p>
                <label className="flex flex-col gap-1">
                  <span className="text-xs text-muted">Nova Senha *</span>
                  <input className="input" type="password" value={newPassword} onChange={e => setNewPassword(e.target.value)} required minLength={8} />
                </label>
                {error && <p className="text-xs text-terracotta">{error}</p>}
                <div className="flex gap-2 pt-1">
                  <button type="button" onClick={() => setModal(null)} className="flex-1 py-2 border border-line text-muted rounded-lg text-sm hover:bg-bg transition-colors">Cancelar</button>
                  <button type="submit" disabled={resetPwM.isPending} className="flex-1 py-2 bg-mineral text-white rounded-lg text-sm font-medium hover:bg-[#3d6180] transition-colors disabled:opacity-60">
                    {resetPwM.isPending ? 'Redefinindo…' : 'Redefinir Senha'}
                  </button>
                </div>
              </form>
            )}

            {/* EXCLUIR */}
            {modal.mode === 'delete' && modal.user && (
              <div className="space-y-4">
                <div className="flex items-center justify-between mb-1">
                  <h3 className="text-base font-semibold text-ink">Excluir Usuário</h3>
                  <button onClick={() => setModal(null)} className="text-muted hover:text-ink"><X className="w-5 h-5" /></button>
                </div>
                <p className="text-sm text-ink-2">Tem certeza que deseja excluir <strong>{modal.user.full_name}</strong>? Esta ação não pode ser desfeita.</p>
                {error && <p className="text-xs text-terracotta">{error}</p>}
                <div className="flex gap-2 pt-1">
                  <button onClick={() => setModal(null)} className="flex-1 py-2 border border-line text-muted rounded-lg text-sm hover:bg-bg transition-colors">Cancelar</button>
                  <button onClick={handleDelete} disabled={deleteM.isPending} className="flex-1 py-2 bg-terracotta text-white rounded-lg text-sm font-medium hover:bg-[#8a3a2e] transition-colors disabled:opacity-60">
                    {deleteM.isPending ? 'Excluindo…' : 'Excluir'}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {toast && (
        <div className="fixed bottom-6 right-6 bg-ink text-white text-sm px-4 py-3 rounded-xl shadow-lg z-50">
          {toast}
        </div>
      )}
    </div>
  )
}
