import EuVatRatePanel from '../components/EuVatRatePanel'

/** Aba "IVA" do admin do mercado europeu: onde a taxa única de IVA é vista e alterada. */
export default function IvaPage() {
  return (
    <div className="min-h-screen bg-bg">
      <div className="mx-auto max-w-4xl px-4 py-6 pb-28 sm:px-6 sm:py-8 md:pb-8">
        <h1 className="mb-6 font-display text-2xl font-semibold text-ink">IVA</h1>
        <EuVatRatePanel scope="market" />
      </div>
    </div>
  )
}
