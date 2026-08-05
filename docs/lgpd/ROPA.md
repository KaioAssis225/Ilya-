# ROPA — Registro das operações de tratamento

**Versão:** 0.1 — inventário técnico inicial
**Data:** 05/08/2026
**Controlador:** Ilya Comércio de Móveis Ltda. — CNPJ 53.836.582/0001-07 —
Rodovia Engenheiro Ermênio de Oliveira Penteado, km 56,5, Itaici,
Indaiatuba/SP — CEP 13340-600
**Responsável e encarregado indicado:** Kaio Vinicius de Assis
**Encarregado substituto:** Julio Santiago Armelin
**Canal:** `privacidadeilya@outlook.com` — `(19) 99406-9071`

> As hipóteses legais abaixo são propostas técnicas. A empresa deve aprová-las
> com jurídico antes de tratá-las como posição legal definitiva.

## Operações

| ID | Operação e titulares | Dados | Finalidade | Hipótese legal proposta | Acesso | Operadores/compartilhamento | Retenção |
|---|---|---|---|---|---|---|---|
| ROPA-01 | Cadastro de cliente | nome, telefone, e-mail opcional, CEP, número, endereço, cidade, UF, representante | elaborar orçamento, gerir pedido, contato, faturamento e logística | procedimentos preliminares/execução de contrato (art. 7º, V); obrigação legal quando aplicável (II) | admin, vendedor, cadastros, produtos; representante apenas vinculados; cliente apenas próprio | Railway; API Ilya; ViaCEP recebe somente o CEP consultado | RET-01 |
| ROPA-02 | Cadastro de representante | nome, telefone, e-mail opcional, endereço completo, desconto | relação comercial, gestão de carteira e pedidos | execução de contrato (V); exercício regular de direitos (VI) | admin e papéis internos autorizados; representante apenas próprio; cliente apenas representante vinculado | Railway | RET-02 |
| ROPA-03 | Contas e autenticação | nome, e-mail sintético ou real, username, hash de senha, role, IDs vinculados, bloqueios, sessões | autenticar, autorizar, prevenir abuso e manter segurança | execução de contrato (V); legítimo interesse em segurança, sujeito a teste de balanceamento (IX) | titular; admin para gestão; backend | Railway; Vercel atua como proxy do frontend | RET-03 e RET-04 |
| ROPA-04 | Orçamentos e pedidos | cliente, representante, itens, preços, descontos, observações, status e timestamps | cotação, contratação, execução, suporte, histórico financeiro/comercial | procedimentos preliminares/contrato (V); obrigação legal (II); exercício regular de direitos (VI) | admin e operadores de venda; representante/cliente somente escopo vinculado; `produtos` atualmente vê todos | Railway; PDF gerado no navegador do usuário | RET-05 |
| ROPA-05 | Histórico e auditoria de pedidos | usuário, ação, detalhes, pedido, data | integridade, rastreabilidade, segurança e defesa em disputas | legítimo interesse sujeito a balanceamento (IX); exercício regular de direitos (VI) | admin e vendedor no histórico global; usuários vinculados no histórico do pedido | Railway | RET-06 |
| ROPA-06 | Notificações | usuário, mensagem, status de leitura e data | informar eventos do pedido e da conta | execução de contrato (V) | somente usuário destinatário; backend | Railway | RET-07 |
| ROPA-07 | Direitos do titular | conta, perfil de segurança, cadastro vinculado, pedidos, notificações, sessões, ações em pedidos, cadastros criados e convites emitidos; senha apenas para reautenticação | confirmação, acesso, exportação, correção e anonimização | cumprimento de obrigação legal/regulatória (II) | titular autenticado; admin no fluxo administrativo de cliente | Railway; arquivo exportado ao dispositivo do titular | RET-08 |
| ROPA-08 | Assinatura eletrônica histórica | imagem de assinatura, hash documental, convite e datas | comprovar aceite contratual | execução de contrato (V); exercício regular de direitos (VI) | feature desativada; dados históricos ainda podem ser acessados por rotas autorizadas | Railway | RET-09 |
| ROPA-09 | Logs técnicos | ID de usuário quando necessário, request ID, rota, resultado, duração e erros sanitizados | segurança, investigação, disponibilidade e diagnóstico | legítimo interesse sujeito a balanceamento (IX); cumprimento de obrigação de segurança | equipe técnica e provedor conforme permissão | Railway/Vercel e máquina de backup | RET-10 |
| ROPA-10 | Backups | cópia integral do banco, arquivos e dados acima | continuidade, recuperação de desastre, integridade e disponibilidade | legítimo interesse em continuidade/segurança (IX); obrigação legal conforme conteúdo | operadores autorizados da empresa | máquina designada, armazenamento off-site e infraestrutura Docker | RET-11 |
| ROPA-11 | Consulta de CEP | CEP informado | preencher endereço e reduzir erro cadastral | procedimentos preliminares/contrato (V) | backend; resposta ao usuário solicitante | ViaCEP recebe o CEP consultado, sem token, nome, e-mail ou IP do navegador | cache/registro técnico conforme RET-10; resposta não possui tabela própria |
| ROPA-12 | Integração por webhook | hoje apenas evento técnico de teste com ID do usuário acionador; eventos futuros ainda não autorizados | testar e futuramente integrar Ilya Estoque | legítimo interesse técnico sujeito a balanceamento; reavaliar antes de dados de negócio | admin e worker | receptor configurado; atualmente feature inerte quando `WEBHOOK_ENABLED=false` | RET-12 |

## Dados que não devem ser inseridos

O sistema não solicita dados de saúde, origem racial, religião, opinião política,
filiação sindical, vida sexual, genética ou biometria. Usuários devem ser
orientados a não inserir dados sensíveis ou documentos pessoais em observações,
mensagens, descrições e campos livres.

## Testes de balanceamento pendentes

Devem ser produzidos testes de legítimo interesse para:

- segurança e prevenção de fraude em autenticação;
- logs técnicos;
- backups e continuidade;
- histórico/auditoria além do prazo contratual;
- integrações técnicas que identifiquem usuários.

Cada teste deve registrar finalidade, necessidade, expectativa do titular,
impacto, salvaguardas, possibilidade de oposição e decisão final.

## Revisões obrigatórias

Revisar o ROPA quando:

- um novo campo pessoal for criado;
- uma role ganhar acesso;
- um fornecedor ou webhook for ativado;
- houver nova finalidade;
- mudar a região de hospedagem;
- a retenção for alterada;
- assinaturas eletrônicas forem reativadas.
