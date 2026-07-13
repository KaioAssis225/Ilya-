export default function PrivacyPolicyPage() {
  return (
    <div className="min-h-screen bg-bg px-4 py-12">
      <div className="max-w-2xl mx-auto">
        <div className="text-center mb-10">
          <p
            className="text-4xl tracking-[0.35em] font-light text-gold"
            style={{ fontFamily: "'Cormorant Garamond', Georgia, serif" }}
          >
            ILYA
          </p>
          <div className="w-16 h-px bg-gold-soft mx-auto mt-2 mb-4" />
          <h1 className="text-lg font-semibold text-ink tracking-wider uppercase">
            Política de Privacidade
          </h1>
          <p className="text-xs text-muted mt-1">Última atualização técnica: 13 de julho de 2026</p>
        </div>

        <div className="bg-white rounded-2xl border border-line shadow-sm p-8 space-y-6 text-sm text-ink-2 leading-relaxed">

          <section>
            <h2 className="text-xs font-bold uppercase tracking-widest text-gold mb-2">1. Responsável pelo Tratamento</h2>
            <p>
              A Ilya Móveis &amp; Estofados ("Ilya") é responsável pelo tratamento dos dados pessoais coletados por meio deste sistema, nos termos da Lei Geral de Proteção de Dados (Lei nº 13.709/2018 — LGPD).
            </p>
            <p className="mt-1">
              Canal de privacidade: <a href="mailto:privacidade@ilya.com" className="text-gold underline">privacidade@ilya.com</a>
            </p>
          </section>

          <section>
            <h2 className="text-xs font-bold uppercase tracking-widest text-gold mb-2">2. Dados Coletados e Finalidades</h2>
            <ul className="list-disc pl-5 space-y-1">
              <li><strong>Nome, telefone e e-mail</strong> — comunicação comercial e formalização de orçamentos.</li>
              <li><strong>Endereço e CEP</strong> — logística e faturamento de produtos.</li>
              <li><strong>Assinatura eletrônica</strong> — formalização de aceite contratual.</li>
              <li><strong>Credenciais de acesso</strong> — autenticação e controle de privilégios no sistema.</li>
            </ul>
            <p className="mt-2">As bases legais devem ser definidas conforme cada finalidade, podendo incluir execução de contrato, cumprimento de obrigação legal e exercício regular de direitos.</p>
          </section>

          <section>
            <h2 className="text-xs font-bold uppercase tracking-widest text-gold mb-2">3. Compartilhamento com Terceiros</h2>
            <p>
              A consulta de CEP é realizada de forma proxiada pelo servidor da Ilya, sem exposição do IP ou identidade do usuário final a serviços externos. Nenhum dado pessoal identificável é comercializado ou compartilhado com parceiros para fins publicitários.
            </p>
          </section>

          <section>
            <h2 className="text-xs font-bold uppercase tracking-widest text-gold mb-2">4. Seus Direitos (Art. 18 da LGPD)</h2>
            <ul className="list-disc pl-5 space-y-1">
              <li><strong>Acesso e confirmação</strong> — consulte os dados ligados à sua conta em <em>Minha Conta → Baixar Meus Dados</em> ou via <code className="bg-bg px-1 rounded">GET /api/v1/auth/my-data</code>.</li>
              <li><strong>Cópia eletrônica</strong> — exporte seus dados em formato JSON mediante nova confirmação de senha via <code className="bg-bg px-1 rounded">POST /api/v1/auth/my-data/export</code>.</li>
              <li><strong>Eliminação</strong> — solicite a anonimização dos seus dados pessoais via <code className="bg-bg px-1 rounded">POST /api/v1/auth/anonymize</code> ou pelo canal <a href="mailto:privacidade@ilya.com" className="text-gold underline">privacidade@ilya.com</a>.</li>
              <li><strong>Retificação</strong> — corrija seus dados cadastrais diretamente no sistema ou pelo canal de privacidade.</li>
            </ul>
          </section>

          <section>
            <h2 className="text-xs font-bold uppercase tracking-widest text-gold mb-2">5. Retenção de Dados</h2>
            <p>
              Os dados pessoais são retidos pelo tempo necessário para a execução contratual e cumprimento de obrigações legais. Após solicitação de exclusão, os dados identificáveis são anonimizados, preservando apenas registros estatísticos e contábeis sem identificação pessoal.
            </p>
          </section>

          <section>
            <h2 className="text-xs font-bold uppercase tracking-widest text-gold mb-2">6. Segurança</h2>
            <p>
              Adotamos controles técnicos como hashing de senhas com Argon2, tokens JWT de curta duração, refresh token em cookie HttpOnly, bloqueio progressivo de login, revogação de sessões, HTTPS em produção, cabeçalhos de segurança HTTP e limites em endpoints e uploads sensíveis. Imagens de assinatura não são mantidas no armazenamento persistente do navegador.
            </p>
          </section>

          <section>
            <h2 className="text-xs font-bold uppercase tracking-widest text-gold mb-2">7. Contato do Encarregado (DPO)</h2>
            <p>
              Para exercer seus direitos ou esclarecer dúvidas sobre o tratamento de dados, entre em contato com nosso Encarregado pelo e-mail <a href="mailto:privacidade@ilya.com" className="text-gold underline">privacidade@ilya.com</a>.
            </p>
          </section>
        </div>
      </div>
    </div>
  )
}
