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
          <p className="text-xs text-muted mt-1">Última atualização técnica: 5 de agosto de 2026</p>
        </div>

        <div className="bg-white rounded-2xl border border-line shadow-sm p-8 space-y-6 text-sm text-ink-2 leading-relaxed">

          <section>
            <h2 className="text-xs font-bold uppercase tracking-widest text-gold mb-2">1. Responsável pelo Tratamento</h2>
            <p>
              A Ilya Comércio de Móveis Ltda., inscrita no CNPJ sob nº 53.836.582/0001-07, com sede na Rodovia Engenheiro Ermênio de Oliveira Penteado, km 56,5, Itaici, Indaiatuba — SP, CEP 13340-600 ("Ilya"), é responsável pelo tratamento dos dados pessoais coletados por meio deste sistema, nos termos da Lei Geral de Proteção de Dados (Lei nº 13.709/2018 — LGPD).
            </p>
            <p className="mt-1">
              Canal de privacidade: <a href="mailto:privacidadeilya@outlook.com" className="text-gold underline">privacidadeilya@outlook.com</a> ou telefone <a href="tel:+5519994069071" className="text-gold underline">(19) 99406-9071</a>.
            </p>
          </section>

          <section>
            <h2 className="text-xs font-bold uppercase tracking-widest text-gold mb-2">2. Dados Coletados e Finalidades</h2>
            <ul className="list-disc pl-5 space-y-1">
              <li><strong>Nome, telefone e e-mail</strong> — comunicação comercial e formalização de orçamentos.</li>
              <li><strong>Endereço e CEP</strong> — logística e faturamento de produtos.</li>
              <li><strong>Dados de pedidos</strong> — elaboração de orçamentos, execução da venda, suporte e preservação do histórico comercial.</li>
              <li><strong>Assinatura eletrônica histórica</strong> — comprovação de aceite contratual; a coleta de novas assinaturas está temporariamente desativada.</li>
              <li><strong>Credenciais de acesso</strong> — autenticação e controle de privilégios no sistema.</li>
              <li><strong>Registros técnicos</strong> — segurança, prevenção de abuso, diagnóstico e continuidade do serviço.</li>
            </ul>
            <p className="mt-2">
              Conforme a finalidade, o tratamento pode ser necessário para procedimentos preliminares e execução de contrato, cumprimento de obrigação legal ou regulatória, exercício regular de direitos e segurança do serviço. Quando a Ilya utilizar legítimo interesse, serão considerados a necessidade, as expectativas do titular, os riscos e as salvaguardas aplicáveis.
            </p>
          </section>

          <section>
            <h2 className="text-xs font-bold uppercase tracking-widest text-gold mb-2">3. Operadores e Compartilhamento</h2>
            <p>
              Para operar o sistema, a Ilya utiliza provedores de infraestrutura e hospedagem, incluindo Vercel no frontend e Railway no backend e banco de dados. Outros provedores de armazenamento somente são utilizados quando configurados pela Ilya. Esses fornecedores tratam dados conforme a prestação técnica contratada e as instruções aplicáveis.
            </p>
            <p className="mt-2">
              A consulta de CEP é intermediada pelo servidor da Ilya: o serviço consultado recebe o CEP informado, mas não recebe o token, nome, e-mail ou IP do navegador. A Ilya não comercializa dados pessoais nem os compartilha para publicidade.
            </p>
            <p className="mt-2">
              Dependendo da região e dos subprocessadores adotados pelos provedores, o tratamento pode envolver transferência internacional. A Ilya deve aplicar as salvaguardas e mecanismos previstos na LGPD e na regulamentação da ANPD.
            </p>
          </section>

          <section>
            <h2 className="text-xs font-bold uppercase tracking-widest text-gold mb-2">4. Seus Direitos (Art. 18 da LGPD)</h2>
            <ul className="list-disc pl-5 space-y-1">
              <li><strong>Acesso e confirmação</strong> — consulte os dados ligados à sua conta em <em>Minha Conta → Baixar Meus Dados</em> ou via <code className="bg-bg px-1 rounded">GET /api/v1/auth/my-data</code>.</li>
              <li><strong>Cópia eletrônica</strong> — exporte seus dados em formato JSON mediante nova confirmação de senha via <code className="bg-bg px-1 rounded">POST /api/v1/auth/my-data/export</code>.</li>
              <li><strong>Eliminação ou anonimização</strong> — clientes e representantes com conta podem usar o recurso disponível em Minha Conta, mediante confirmação da senha; demais titulares podem solicitar pelo canal de privacidade. Dados necessários para obrigação legal, exercício de direitos ou outra hipótese de conservação podem ser preservados de forma limitada.</li>
              <li><strong>Retificação</strong> — corrija seus dados cadastrais diretamente no sistema ou pelo canal de privacidade.</li>
              <li><strong>Informações sobre compartilhamento e oposição</strong> — solicite esclarecimentos sobre operadores, bases legais e tratamentos aplicáveis ao seu caso.</li>
            </ul>
            <p className="mt-2">
              A opção <strong>Remover Meu Acesso</strong> elimina a conta usada para entrar no sistema e encerra as sessões. Ela não significa, por si só, a eliminação de pedidos, cadastros comerciais ou documentos cuja conservação seja necessária.
            </p>
          </section>

          <section>
            <h2 className="text-xs font-bold uppercase tracking-widest text-gold mb-2">5. Retenção de Dados</h2>
            <p>
              Clientes sem pedido são mantidos por até 2 anos após o último contato. Representantes são mantidos durante a relação com a Ilya e por 5 anos após o encerramento. Orçamentos não convertidos são mantidos por 2 anos após a última atualização. Pedidos finalizados ou cancelados, seus históricos e eventuais assinaturas são mantidos por até 10 anos e depois têm os dados pessoais eliminados ou anonimizados, preservado apenas o mínimo legalmente necessário.
            </p>
            <p className="mt-2">
              Sessões expiram tecnicamente; evidências de refresh token são descartadas após o período de auditoria configurado. Backups criptografados seguem ciclos diário, semanal e mensal. Quando houver disputa, cobrança, garantia, fiscalização, investigação ou obrigação legal, a eliminação pode ser suspensa até o encerramento da necessidade. A Ilya informará eventual impedimento e restringirá o uso ao propósito que justificou a conservação.
            </p>
          </section>

          <section>
            <h2 className="text-xs font-bold uppercase tracking-widest text-gold mb-2">6. Segurança</h2>
            <p>
              Adotamos controles técnicos como hashing de senhas com Argon2, tokens JWT de curta duração, refresh token em cookie HttpOnly, bloqueio de login, revogação de sessões, HTTPS em produção, controle de acesso por função, cabeçalhos de segurança, limites de requisição e backups criptografados e testados. Imagens de assinatura não são mantidas no armazenamento persistente do navegador.
            </p>
          </section>

          <section>
            <h2 className="text-xs font-bold uppercase tracking-widest text-gold mb-2">7. Canal de Privacidade</h2>
            <p>
              O encarregado é <strong>Kaio Vinicius de Assis</strong>, tendo <strong>Julio Santiago Armelin</strong> como substituto. Para exercer direitos, apresentar reclamações ou esclarecer dúvidas sobre o tratamento de dados, entre em contato pelo e-mail <a href="mailto:privacidadeilya@outlook.com" className="text-gold underline">privacidadeilya@outlook.com</a> ou pelo telefone <a href="tel:+5519994069071" className="text-gold underline">(19) 99406-9071</a>. O canal é verificado a cada quatro horas.
            </p>
          </section>
        </div>
      </div>
    </div>
  )
}
