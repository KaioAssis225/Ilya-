import { UserCheck } from 'lucide-react'
import ClientesDashboardContent from '../components/ClientesDashboardContent'
import { useCadastroText } from '../hooks/useCadastroText'

/** Dashboard de Clientes (Portugal), em página própria com entrada no menu. */
export default function ClientesDashboardPage() {
  const tx = useCadastroText()
  return (
    <div className="min-h-screen bg-bg">
      <div className="max-w-6xl mx-auto px-4 md:px-6 py-6 md:py-8">
        <div className="mb-6">
          <h1 className="font-display text-2xl font-semibold text-ink flex items-center gap-2">
            <UserCheck className="w-6 h-6 text-gold" /> {tx('Clientes')}
          </h1>
          <p className="text-sm text-muted mt-1">{tx('Quem já foi contactado e quem ainda falta contactar.')}</p>
        </div>

        <ClientesDashboardContent />
      </div>
    </div>
  )
}
