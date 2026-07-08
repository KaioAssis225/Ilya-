filepath = r"C:\Users\matheus.cardoso\Documents\Programador\Projeto Ilya\Alto Comando\Salão de Conferência.md"

with open(filepath, 'r', encoding='utf-8') as f:
    text = f.read()

# Let's replace the item 5 text block with empty string
to_remove = """            - Em vez de validar apenas a palavra exata `"Conjunto"`, flexibilizar a detecção tanto no backend quanto no frontend usando a verificação de substring case-insensitive para o termo `"conjunto"`. Isso garante que novos tipos de móveis registrados sob qualquer grupo que contenham a palavra "conjunto" (ex: `"Conjunto de Jantar"`, `"Conjuntos"`) acionem automaticamente o fluxo de componentes livres."""

text = text.replace(to_remove, "")
text = text.replace("         5. **Lógica de Identificação de Conjuntos Flexível (Criação de Subgrupos/Tipos)**:", "")

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(text)

print("Salão de Conferência.md limpo com sucesso!")
