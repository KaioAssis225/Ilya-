filepath = r"C:\Users\matheus.cardoso\Documents\Programador\Projeto Ilya\Alto Comando\Salão de Conferência.md"

with open(filepath, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find where Tópico 73 objectives list has item 5
new_lines = []
skip = False
for line in lines:
    if "5. **Lógica de Identificação de Conjuntos Flexível" in line:
        skip = True
        continue
    if skip and "acessos e senha padrao" in line.lower(): # skip the description lines
        continue
    if skip and "acione automaticamente o fluxo de componentes livres" in line:
        skip = False
        continue
    new_lines.append(line)

# Let's write the file back
with open(filepath, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

# Now, append Tópico 74 at the very end
with open(filepath, 'a', encoding='utf-8') as f:
    f.write("""
---

### Tópico 74: Inicialização do Bloco 74 — Lógica de Identificação de Conjuntos Flexível (Criação de Subgrupos/Tipos)
*   **Gemini (Planejador):** Claude, vamos iniciar a especificação do **Bloco 74 (Lógica de Identificação de Conjuntos Flexível)** para atender à solicitação de tipos dinâmicos do usuário.

    *   *Objetivos do Bloco 74:*
        1. **Mecanismo Flexível no Frontend (CadastroPage.tsx & ProdutosPage.tsx)**:
           - Criar a função `isConjuntoType(type)` para identificar se o nome do tipo contém a substring "conjunto" (case-insensitive).
           - Substituir todas as verificações estritas do tipo `'Conjunto'` pela nova lógica dinâmica, ativando a modelagem e exibição de componentes livres.
        2. **Segurança de Modelagem no Backend (products.py)**:
           - Adaptar as rotas de criação e atualização de produtos para usar busca case-insensitive por substring (`"conjunto" in type.lower()`) ao validar se um produto deve conter componentes livres e impedir auto-referência em sub-itens.

    *   *Instrução de parada:* Implemente a lógica de identificação flexível de conjuntos no frontend e backend, teste o fluxo criando novos tipos contendo a palavra "conjunto" e valide o funcionamento antes de finalizar seu turno.
""")

print("Salão de Conferência.md atualizado com sucesso via script!")
