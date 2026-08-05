# Relatório consolidado de adequação à LGPD — Projeto Ilya

**Data de consolidação:** 05/08/2026
**Controlador:** Ilya Comércio de Móveis Ltda.
**CNPJ:** 53.836.582/0001-07
**Responsável e encarregado:** Kaio Vinicius de Assis
**Substituto:** Julio Santiago Armelin
**Canal:** `privacidadeilya@outlook.com` — monitoramento a cada 4 horas
**Escopo técnico:** branch `codex/analise-lgpd-2026-08-05`

## 1. Conclusão executiva

O projeto passou a possuir uma base técnica consistente de privacidade:

- identificação do controlador, encarregado, substituto e canal;
- política pública e documentos internos de governança;
- trilha estruturada das operações de privacidade;
- exportação, remoção de acesso e anonimização com reautenticação;
- legal hold e simulações de retenção não destrutivas;
- marcos canônicos de atividade e encerramento;
- registro estruturado de incidentes por no mínimo cinco anos;
- inventário de dez categorias de retenção;
- controles administrativos sem exclusão automática.

Isso reduz riscos e fornece evidência operacional, mas **não representa
certificação nem garantia absoluta de conformidade**. Contratos, validações
jurídicas, treinamento, configuração dos provedores e execução dos processos
continuam sendo responsabilidades da empresa.

## 2. Identificação e governança

Foram documentados:

- endereço: Rodovia Engenheiro Ermênio de Oliveira Penteado, km 56,5, Itaici,
  Indaiatuba — SP, CEP 13340-600;
- ato de designação do encarregado;
- encarregado substituto;
- frequência de monitoramento do canal;
- ROPA inicial;
- matriz de acesso;
- matriz de retenção;
- playbook de incidentes;
- política e procedimento de retenção;
- pendências que não podem ser resolvidas pelo código.

Documentos principais:

- `ATO-DESIGNACAO-ENCARREGADO.md`;
- `ROPA.md`;
- `MATRIZ-ACESSO.md`;
- `MATRIZ-RETENCAO.md`;
- `PLAYBOOK-INCIDENTES-LGPD.md`;
- `OPERACAO-RETENCAO.md`;
- `PROCEDIMENTO-DESLIGAMENTO-E-ACESSOS.md`;
- `MODELOS-COMUNICACAO-INCIDENTE.md`;
- `CHECKLIST-FORNECEDORES.md`;
- `MODELO-LIA.md`;
- `PENDENCIAS-EMPRESA.md`.

## 3. Direitos dos titulares

### 3.1 Exportação

A exportação reúne o perfil do usuário e dados relacionados sem expor:

- hash de senha;
- token de acesso ou refresh;
- token de convite;
- segredos de integração.

### 3.2 Remoção da conta de acesso

A remoção da credencial é diferente da eliminação de registros comerciais. O
fluxo:

- exige senha atual;
- revoga sessões;
- registra evento de privacidade;
- preserva dados sujeitos a obrigação fiscal, comercial ou legal.

### 3.3 Anonimização

Cliente e representante podem ser anonimizados nos fluxos autorizados. A
anonimização:

- substitui dados identificáveis;
- mantém chaves necessárias à integridade dos pedidos;
- desativa contas vinculadas;
- revoga sessões;
- registra autor, fundamento, resultado e correlação.

## 4. Auditoria de privacidade

A tabela `privacy_events` registra operações relevantes de maneira minimizada:

- ator;
- tipo e identificador do titular/objeto;
- ação;
- resultado;
- fundamento;
- request ID;
- contexto técnico limitado;
- data.

O código foi orientado a não copiar senhas, tokens, arquivos exportados,
documentos ou conteúdo pessoal desnecessário para a trilha.

## 5. Retenção e ciclo de vida

### 5.1 Marcos canônicos

Foram adicionados:

- `clients.last_activity_at`;
- `representatives.relationship_ended_at`;
- `orders.finalized_at`;
- `orders.cancelled_at`;
- `notifications.read_at`;
- `integration_outbox.dead_lettered_at`.

Registros históricos recebem backfill conservador. Constraints no banco
garantem coerência entre status e timestamps.

### 5.2 Prazos aplicados à simulação

| Categoria | Prazo/marco |
|---|---|
| Cliente sem pedido e sem conta ativa | 2 anos após última atividade |
| Orçamento/pedido aberto | 2 anos após última atualização |
| Pedido finalizado/cancelado | 10 anos após o estado terminal |
| Representante | 5 anos após encerramento do vínculo |
| Notificação lida | 90 dias após leitura |
| Notificação não lida | 365 dias após criação |
| Convite de assinatura | 30 dias após expiração, consumo ou revogação |
| Webhook entregue | 90 dias após entrega |
| Webhook em `dead_letter` | até resolução manual; sem exclusão automática |
| Evento de privacidade | 5 anos após criação, seguido de revisão |

### 5.3 Legal hold

O administrador pode bloquear cliente, representante ou pedido quando houver:

- disputa;
- cobrança;
- garantia;
- fiscalização;
- investigação;
- ordem ou obrigação legal.

Holds de cliente e representante alcançam registros derivados quando o vínculo
é identificável. A liberação exige senha e justificativa.

### 5.4 Dry-run e aprovação

O relatório:

- conta vencidos, bloqueados e candidatos;
- guarda uma fotografia auditável;
- limita a fotografia a 5.000 candidatos;
- impede aprovação de fotografia truncada;
- exige senha para aprovação;
- não oferece execução ou exclusão.

Nenhum dado real foi descartado durante esta adequação.

## 6. Encerramento de representantes

O encerramento do vínculo:

- é exclusivo de administrador;
- exige senha, data e justificativa;
- registra o marco de retenção;
- desativa usuários vinculados;
- incrementa a versão de autenticação;
- revoga refresh tokens ativos;
- produz evento de auditoria.

## 7. Registro de incidentes

Foi criada a área **Admin → Registro de incidentes LGPD**, contendo:

- data da ciência;
- descrição das circunstâncias;
- categorias de dados;
- quantidade de titulares;
- avaliação de risco e danos;
- mitigação;
- decisão e detalhes de comunicação à ANPD/titulares;
- referências de evidências;
- causa raiz;
- ações corretivas;
- estado e encerramento.

O encerramento exige causa raiz e ações corretivas. O banco impede prazo de
guarda inferior a cinco anos. Não existe endpoint de exclusão.

## 8. Segurança e minimização

Controles relacionados que sustentam o programa:

- autenticação e autorização por papéis;
- revogação de sessões e `auth_version`;
- confirmação de senha em ações sensíveis;
- auditoria por request ID;
- CSP, CORS, CSRF e cabeçalhos de segurança;
- hashes de tokens e convites;
- limitação de taxa em endpoints sensíveis;
- consultas parametrizadas via SQLAlchemy;
- minimização das projeções de listagem;
- backup criptografado e política GFS documentada;
- integração por transactional outbox, sem acoplamento direto ao outro banco.

## 9. Migrações desta adequação

| Migração | Entrega |
|---|---|
| `0040` | trilha estruturada de eventos de privacidade |
| `0041` | legal holds e relatórios não destrutivos |
| `0042` | marcos canônicos de clientes, representantes e pedidos |
| `0043` | registro obrigatório de incidentes |
| `0044` | marcos auxiliares de notificações e webhooks |

Todas devem ser aplicadas em sequência por `alembic upgrade head`.

## 10. Rotina operacional

### A cada 4 horas

- verificar `privacidadeilya@outlook.com`;
- registrar e encaminhar solicitações;
- ativar o playbook diante de incidente.

### Semanalmente

- verificar falhas de backup;
- revisar `dead_letter`;
- verificar incidentes abertos e prazos de comunicação.

### Mensalmente

- gerar dry-run de retenção;
- revisar legal holds;
- revisar administradores e contas inativas;
- registrar decisões e exceções.

### Trimestralmente

- revisar as roles `admin` e `produtos`;
- revisar fornecedores e subprocessadores;
- verificar acessos incompatíveis;
- revisar a necessidade dos dados tratados.

### Anualmente

- revisar ROPA, matriz de acesso e retenção;
- revisar o playbook;
- executar simulado de incidente;
- revisar treinamento, contratos e política pública.

O primeiro simulado está agendado para 10/10/2026.

## 11. Validações técnicas executadas

- suíte completa do backend: **196 testes aprovados**;
- lint e build de produção do frontend;
- compilação das aplicações;
- migrações completas em PostgreSQL temporário;
- downgrade/reaplicação das migrações críticas;
- consulta real do dry-run com todas as dez categorias;
- validação de índices e constraints;
- teste de rejeição de retenção de incidente inferior a cinco anos.

## 12. Pendências externas

O código não pode concluir sozinho:

- revisão do ROPA pelo comercial;
- aprovação das bases legais e LIAs pelo jurídico;
- avaliação formal de eventual dispensa do encarregado;
- contratos/DPA e subprocessadores de Railway, Vercel, storage e backup;
- confirmação da retenção de logs nos provedores;
- enquadramento do art. 15 do Marco Civil;
- revisão nominativa dos administradores;
- treinamento e termos de confidencialidade;
- acesso operacional ao canal da ANPD;
- aprovação jurídica dos modelos de comunicação;
- teste documentado de restauração do backup;
- assinatura formal das políticas e decisões.

Esses itens permanecem discriminados em `PENDENCIAS-EMPRESA.md`.

## 13. Regra para futuras alterações

Toda funcionalidade que introduza novo dado pessoal, fornecedor, finalidade,
integração ou forma de compartilhamento deve revisar antes do deploy:

1. ROPA;
2. base legal;
3. transparência ao titular;
4. matriz de acesso;
5. retenção e descarte;
6. operadores e contratos;
7. riscos e resposta a incidentes;
8. testes de autorização e auditoria.

Nenhum job destrutivo deve ser ativado apenas porque um registro apareceu no
dry-run. A elegibilidade, o legal hold e a autorização precisam ser
revalidados no momento da futura execução.
