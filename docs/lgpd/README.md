# Programa de privacidade — Projeto Ilya

Esta pasta reúne os controles de governança da Fase 1 de adequação à LGPD.
Os documentos refletem o sistema analisado no commit `b21b765`, em 05/08/2026.

## Documentos

- [ROPA](./ROPA.md): registro das operações de tratamento.
- [Matriz de retenção](./MATRIZ-RETENCAO.md): critérios de guarda e descarte.
- [Operação de retenção](./OPERACAO-RETENCAO.md): legal hold, simulação e
  aprovação sem descarte.
- [Matriz de acesso](./MATRIZ-ACESSO.md): necessidade de acesso por papel.
- [Playbook de incidentes](./PLAYBOOK-INCIDENTES-LGPD.md): resposta e comunicação.
- [Proposta de prazos auxiliares](./PROPOSTA-PRAZOS-AUXILIARES.md): recomendações
  ainda dependentes de aprovação.
- [Ato de designação do encarregado](./ATO-DESIGNACAO-ENCARREGADO.md): minuta para aprovação formal.
- [Pendências da empresa](./PENDENCIAS-EMPRESA.md): decisões que o código não pode tomar.

## Estado da Fase 1

| Entrega | Estado |
|---|---|
| Responsável interno e encarregado/dispensa | Kaio Vinicius de Assis designado; Julio Santiago Armelin é o substituto; aprovação registrada |
| Canal de privacidade | `privacidadeilya@outlook.com`; verificação a cada 4 horas |
| ROPA inicial | Criado; bases legais aguardam validação jurídica |
| Política de privacidade | Atualizada tecnicamente; identificação jurídica aguarda validação |
| Matriz de retenção | Prazos de clientes, representantes, orçamentos, pedidos e assinaturas aprovados |
| Playbook de incidentes | Criado |
| Revisão da role `produtos` | Manutenção do acesso amplo aprovada pelo responsável em 05/08/2026 |
| Texto de exclusão de conta | Corrigido para distinguir acesso de dados comerciais |

## Controles técnicos posteriores já implementados na branch

- remoção da conta de acesso exige confirmação da senha atual;
- anonimização exige confirmação da senha atual;
- anonimização self-service disponível para cliente e representante;
- exportação inclui perfil de segurança, sessões retidas, ações em pedidos,
  cadastros criados e convites de assinatura emitidos, sem expor hashes/tokens;
- interface diferencia remoção do acesso e anonimização dos dados.
- trilha persistente registra exportação, anonimização e remoção de acesso com
  identificador de correlação, autor, titular, fundamento e resultado;
- a trilha não copia senha, token, arquivo exportado ou conteúdo pessoal;
- anonimização administrativa está disponível para clientes e representantes,
  com desativação de todas as contas ativas vinculadas.
- legal hold e relatórios `dry-run` estão disponíveis somente para
  administradores; aprovar um relatório não executa descarte.
- o painel **Admin → Governança de retenção** permite gerar, revisar, bloquear
  e aprovar as fotografias sem disponibilizar ações destrutivas.
- clientes, representantes e pedidos possuem marcos canônicos de ciclo de vida;
  a simulação não depende mais de timestamps técnicos para registros encerrados.
- o encerramento administrativo do representante exige senha e justificativa,
  desativa os acessos vinculados e revoga seus refresh tokens.
- o registro estruturado de incidentes fica restrito ao administrador, conserva
  os campos regulatórios mínimos por pelo menos cinco anos e não oferece
  exclusão pela API.

## Regra de manutenção

Toda nova funcionalidade que trate dados pessoais deve atualizar, antes do
deploy:

1. o ROPA;
2. a matriz de retenção;
3. a matriz de acesso, se houver nova permissão;
4. a política pública, se mudar o que é informado ao titular;
5. o playbook, se surgir novo fornecedor, canal ou risco de incidente.

O responsável pela alteração deve registrar a data, o motivo e a aprovação da
empresa. Placeholders não podem ser publicados como se fossem fatos.
