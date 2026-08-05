# Playbook de incidentes com dados pessoais

**Versão:** 1.1
**Data:** 05/08/2026
**Referência:** LGPD art. 48 e Resolução CD/ANPD nº 15/2024.

## 1. Quando ativar

Ative este playbook diante de evento confirmado ou suspeito que possa afetar
confidencialidade, integridade, disponibilidade ou autenticidade de dados
pessoais, incluindo:

- conta invadida ou permissão excessiva;
- banco, backup, log ou arquivo exposto;
- envio ao cliente/representante errado;
- perda, corrupção ou indisponibilidade relevante;
- ransomware, malware ou segredo vazado;
- acesso interno sem necessidade;
- webhook ou fornecedor recebendo dados indevidos.

Suspeita deve ser tratada imediatamente; a classificação pode mudar durante a
investigação.

## 2. Papéis

| Papel | Responsabilidade | Titular designado |
|---|---|---|
| Coordenador do incidente | abre registro, controla tempo, decisões e encerramento | Kaio Vinicius de Assis |
| Técnico | contém, preserva evidências, investiga e recupera | Kaio Vinicius de Assis; acionar apoio especializado conforme o incidente |
| Controlador/gestão | decide risco, comunicação e recursos | Kaio Vinicius de Assis |
| Encarregado/canal LGPD | orienta, recebe titulares e acompanha ANPD | Kaio Vinicius de Assis |
| Jurídico | valida obrigação e conteúdo das comunicações | Kaio Vinicius de Assis coordena; consultoria jurídica externa deve ser acionada quando necessário |
| Comunicação | envia aviso individual e atende dúvidas | Kaio Vinicius de Assis |
| Fornecedor afetado | entrega logs, escopo, medidas e cooperação | Railway/Vercel/outro conforme caso |

Ninguém deve esperar o preenchimento de todos os papéis para conter uma ameaça.
Na indisponibilidade de Kaio Vinicius de Assis, o encarregado substituto é
**Julio Santiago Armelin**.

## 3. Linha do tempo

### Primeiras 2 horas

1. Abra um ID de incidente e registre data/hora da ciência.
2. Preserve logs, request IDs, configurações, versões e evidências.
3. Não apague registros nem altere produção sem registrar a ação.
4. Contenha: revogue sessões/segredos, suspenda integração, restrinja acesso ou
   isole o componente.
5. Acione coordenador, técnico, gestão e encarregado/jurídico.
6. Registre quem fez cada ação e o resultado.

### Até 24 horas

1. Confirme se há dados pessoais e identifique:
   - categorias e quantidade de titulares;
   - natureza e quantidade dos dados;
   - período e sistemas afetados;
   - acesso, cópia, alteração, perda ou indisponibilidade;
   - criptografia/pseudonimização existente;
   - países, fornecedores e terceiros envolvidos.
2. Avalie danos materiais, morais, reputacionais, fraude e roubo de identidade.
3. Classifique se pode causar risco ou dano relevante.
4. Solicite ao operador informações sem demora injustificada.
5. Prepare comunicação preliminar, se aplicável.

### Prazo regulatório

Quando houver risco ou dano relevante, o controlador deve comunicar **ANPD e
titulares em até 3 dias úteis**, contados nos termos da regulamentação aplicável.
Se faltarem informações, a comunicação pode ser preliminar e deve ser
complementada de forma fundamentada em até **20 dias úteis**.

O relógio não deve ser reiniciado porque o fornecedor respondeu tarde. Registre
a data em que o controlador tomou conhecimento e qualquer justificativa.

## 4. Critério de comunicação

Comunicar quando existirem cumulativamente:

1. incidente confirmado;
2. dados pessoais sujeitos à LGPD;
3. possibilidade de risco ou dano relevante.

Considere maior risco quando houver larga escala, dados sensíveis, crianças,
idosos, credenciais, assinaturas, fraude, discriminação, roubo de identidade ou
dados desprotegidos. A decisão de não comunicar deve ser fundamentada e
aprovada, nunca implícita.

## 5. Conteúdo mínimo ao titular

Use linguagem simples, direta e individual sempre que possível:

- natureza e categorias de dados;
- data do conhecimento;
- riscos e possíveis impactos;
- medidas de proteção existentes;
- medidas tomadas ou planejadas;
- motivo de eventual demora;
- ações que o titular pode adotar;
- contato do encarregado/canal.

Não inclua segredo, senha, token, dados de outro titular ou detalhes que
facilitem exploração.

## 6. Registro obrigatório

Para todo incidente, comunicado ou não, guardar:

- ID, datas, sistemas, versão e ambiente;
- responsável e participantes;
- evidências preservadas e cadeia de custódia;
- dados/titulares afetados;
- avaliação de risco e decisão;
- medidas de contenção e recuperação;
- comunicações e comprovantes;
- causa raiz;
- ações corretivas, dono e prazo;
- data de encerramento e aprovação.

O registro deve ser mantido por **no mínimo cinco anos contados da data do
registro**, inclusive quando o incidente não for comunicado à ANPD ou aos
titulares. O sistema calcula e bloqueia esse prazo mínimo no momento da
abertura. Obrigações adicionais ou legal hold podem exigir conservação maior.

O cadastro fica em **Admin → Registro de incidentes LGPD** e não possui endpoint
de exclusão. Alterações de estado e abertura também geram evento de auditoria.

## 7. Contatos a preencher antes de produção

| Contato | Nome | Telefone | E-mail |
|---|---|---|---|
| Gestão/controlador | Kaio Vinicius de Assis | (19) 99406-9071 | privacidadeilya@outlook.com |
| Encarregado/canal LGPD | Kaio Vinicius de Assis | (19) 99406-9071 | privacidadeilya@outlook.com |
| Encarregado substituto | Julio Santiago Armelin | obter no cadastro interno | usar o canal oficial |
| Técnico | Kaio Vinicius de Assis | (19) 99406-9071 | privacidadeilya@outlook.com |
| Jurídico | coordenação por Kaio; apoio externo a contratar/indicar | (19) 99406-9071 | privacidadeilya@outlook.com |
| Railway | verificar contrato/painel | — | suporte do contrato |
| Vercel | verificar contrato/painel | — | suporte do contrato |

Canal oficial da ANPD:
[Comunicação de Incidente de Segurança](https://www.gov.br/anpd/pt-br/canais_atendimento/agente-de-tratamento/comunicado-de-incidente-de-seguranca-cis).

## 8. Encerramento

O incidente só encerra após:

- serviço e integridade validados;
- sessões/segredos comprometidos revogados;
- causa raiz registrada;
- titulares e ANPD comunicados quando necessário;
- ações corretivas com responsáveis e prazos;
- ROPA, risco, contrato e treinamento atualizados;
- reunião de lições aprendidas.

O primeiro simulado está agendado para **10/10/2026**. Depois dele, realizar um
simulado ao menos uma vez por ano e sempre após mudança relevante de
infraestrutura.
