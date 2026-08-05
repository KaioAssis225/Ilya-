# Matriz de acesso a dados pessoais

**Data:** 05/08/2026
**Princípio:** negar por padrão e conceder apenas o necessário à função.

## Acesso atual

| Papel | Clientes | Representantes | Pedidos | Usuários | Dashboard | Justificativa/ação |
|---|---|---|---|---|---|---|
| `admin` | todos, inclusive anonimização/exclusão | todos | todos e exclusão | gestão completa | por padrão | administração; usar conta nominativa e evitar uso diário |
| `vendedor` interno | todos | leitura e edição permitidas | todos e histórico global | sem administração | somente com flag | operação comercial; confirmar necessidade de editar representante |
| `representante` | somente vinculados | somente próprio | somente vinculados | criação de conta para cliente vinculado | somente com flag | gestão da própria carteira |
| `cliente` | somente próprio | apenas representante vinculado | somente próprios | somente própria conta | somente com flag | portal do titular |
| `cadastros` | todos | leitura | sem acesso geral a pedidos | sem administração | somente com flag | qualidade cadastral; confirmar se endereço completo é necessário |
| `produtos` | todos | todos em leitura | todos | sem administração | somente com flag | acesso amplo foi solicitado como “quase administrador”; falta justificativa formal por finalidade |
| `executivo` | sem diretório | sem diretório | sem pedidos | sem administração | sim | visão agregada; respostas não devem expor PII desnecessária |

Somente `admin` acessa a governança de retenção, cria/libera legal holds,
aprova simulações e registra o encerramento do vínculo de representantes. O
encerramento exige reautenticação e revoga os acessos vinculados.

## Decisão necessária para `produtos`

O código atual concede a `produtos` acesso aos diretórios completos e a todos os
pedidos. O contexto do projeto indica que esse papel foi intencionalmente
definido como próximo de administrador. Isso documenta a origem da regra, mas
**não substitui a aprovação de necessidade pela empresa**.

Decisão informada pelo responsável:

- [x] **Manter acesso completo:** a função participa da operação comercial e
  precisa consultar dados pessoais identificáveis. Registrar exemplos e revisar
  trimestralmente.
- [ ] **Minimizar:** manter catálogo e dados agregados; ocultar telefone, e-mail,
  endereço, observações pessoais e identificação do cliente quando não forem
  necessários.

**Responsável:** Kaio Vinicius de Assis
**Data da decisão:** 05/08/2026
**Justificativa:** a role `produtos` é responsável pelo controle geral dos
pedidos e dos cadastros de clientes e representantes. Por isso, o acesso
identificável é considerado necessário para a função atual.

Esta decisão deve ser revisada trimestralmente e sempre que as atribuições da
role mudarem. A aprovação não autoriza exportação ou uso fora da finalidade.

## Controles organizacionais obrigatórios

- conta individual; é proibido compartilhar login;
- revisão trimestral de usuários `admin` e `produtos`;
- revogação de acesso no mesmo dia do desligamento ou troca de função;
- treinamento de confidencialidade e LGPD;
- proibição de exportar dados para planilhas/dispositivos pessoais sem
  autorização;
- registro e investigação de acessos incompatíveis com a função;
- MFA deve ser avaliado para `admin`, `produtos` e demais papéis internos.
