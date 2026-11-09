# TECIDO FORNECIDO (Portugal)

Nos produtos IBTW de Portugal que constam da planilha "Sem tecido", a aplicação
de **tecidos IBTW** passa a ter a opção **TECIDO FORNECIDO** (o cliente traz o
próprio tecido). Ao escolhê-la no orçamento:

1. aparece, só para leitura, **Tecido necessário: 13,2 m** (coluna `MTS TECIDO`);
2. o preço unitário vira o preço "sem tecido" da planilha para a **tabela do
   orçamento** (PVP, Lojista, Arquiteto ou Corporativo). Desconto e IVA seguem
   como sempre, em cima desse preço.

## Regras

- **Quem decide o valor é o servidor.** O front só mostra. Ao criar ou editar o
  pedido, preço e metragem saem do banco; qualquer preço enviado pelo navegador é
  ignorado. O item guarda o preço e a metragem (`order_items.supplied_fabric_meters`)
  e a escolha (`order_item_optional_choices.supplied_fabric`), então o pedido
  continua igual mesmo se a planilha mudar depois. Editar ou revisar o pedido
  recalcula pelo valor de hoje.
- A opção só aparece em produto **EU** com dados importados e só na aplicação da
  categoria `TECIDOS_IBTW`. Produto fora da planilha não ganha a opção; tentar
  usá-la devolve 422.
- O preço da planilha é "sem tecido" e vale para o produto todo: se o produto tem
  mais de uma aplicação de tecido IBTW, escolher TECIDO FORNECIDO em uma marca as
  outras; misturar com outro tecido do cadastro é recusado (422).
- Preços da planilha têm muitas casas decimais: a API arredonda para 2 casas com
  `ROUND_HALF_UP` (4283,235 → 4283,24). O `.xlsx` guarda 17 dígitos
  (4283,2349999999997); o script usa os 15 que o Excel mostra.
- Brasil não é afetado.

## Cadastrar na tela (produto novo ou existente)

Em **Cadastro > Produtos** (Portugal), na ficha do produto, quando a categoria
**Tecidos IBTW** está marcada aparece a seção **TECIDO FORNECIDO**: "Tecido
necessário (m)" e o preço "sem tecido" de cada tabela (PVP, Lojista, Arquiteto,
Corporativo).

- Tudo preenchido → ao salvar, o orçamento passa a oferecer a opção.
- Tudo vazio num produto que tinha dados → ao salvar, a opção é retirada.
- Meio preenchido → não salva e pede para completar.
- Produto com a categoria e sem dados → só um aviso, o produto salva normalmente.
- Quem edita: **admin** e **produtos** (o servidor devolve 403 aos demais:
  `PUT`/`DELETE /api/v1/products/{id}/supplied-fabric`). Metragem > 0, preços ≥ 0,
  2 casas decimais. Pedidos já feitos não mudam.

A opção funciona nos dois jeitos de configurar o produto: com **aplicação** de
tecido IBTW e com o **seletor antigo** (categoria direta no produto). No seletor
antigo o valor escolhido é o texto `TECIDO FORNECIDO`, guardado no item.

## Onde ficam os dados

Tabela nova `product_supplied_fabric` (um registro por produto EU: metragem e os 4
preços), em vez de colunas em `product_markets`. Motivo: só uma parte do catálogo
tem esses dados e `product_markets` é lida em todo cálculo de preço/IVA; a tabela
própria não mexe nessa leitura crítica e se apaga sem tocar o resto. A migration
`supplied_fabric_eu_r42` cria só a estrutura, **sem dados**.

## Importar a planilha (passo a passo)

Precisa de uma conta de **plataforma** (`platform_admin`), a mesma usada nas fotos
órfãs. Nada disso roda sozinho: é você quem executa, depois do merge e do deploy
do backend (a migration roda no deploy).

1. Depois do deploy, confira que o backend subiu normalmente.
2. No terminal, na pasta do projeto, **simule** (não grava nada):

   ```bash
   py ops/importar_tecido_fornecido.py "C:\Users\matheus.cardoso\Downloads\Sem tecido ofc 09 11 2026.xlsx"
   ```

   Digite usuário e senha da conta de plataforma. O resumo mostra quantos serão
   **criados**, **atualizados**, **ignorados** (código que não existe no EU) e
   **com TECIDOS_IBTW** (em aplicação ou no seletor antigo: a opção aparece) e
   **avisos** (produto sem `TECIDOS_IBTW` em nenhum dos dois: a opção não aparece
   nele até o produto ter essa categoria). O relatório completo fica em `logs/tecido-fornecido/`.
3. Confira o relatório. Se houver "IGNORADO_NAO_EXISTE_NO_EU", são códigos da
   planilha que não estão no catálogo de Portugal: nada quebra, só ficam de fora.
   Se **todos** vierem como aviso de "sem TECIDOS_IBTW", a categoria de tecidos IBTW
   deste ambiente provavelmente tem outro código: pare e avise antes de gravar.
4. Grave tudo:

   ```bash
   py ops/importar_tecido_fornecido.py "C:\Users\matheus.cardoso\Downloads\Sem tecido ofc 09 11 2026.xlsx" --apply
   ```

   O script simula de novo, mostra o resumo e pede para digitar `IMPORTAR`.
5. Abra um orçamento em Portugal com um produto da planilha, escolha TECIDO
   FORNECIDO e confira a metragem e o preço contra a linha da planilha.

Importar de novo é seguro: cria o que falta, atualiza o que mudou e nunca apaga um
produto que ficou fora do arquivo. Para tirar a opção de um produto, apague a linha
dele em `product_supplied_fabric` (não há tela para isso nesta entrega).

Sem o script: `POST /api/v1/markets/EU/supplied-fabric/import` (CSV `;` com as
colunas `COD;PVP;LOJISTA;ARQUITETO;CORPORATIVO;MTS TECIDO`), sessão de plataforma,
`dry_run=true` por padrão.

## Fora do escopo

Sem Estoque, outbox ou webhooks. Não há tela de cadastro da metragem/preços por
produto (entra só pela importação). A planilha **não** vai para o repositório.
