filepath = r"C:\Users\matheus.cardoso\Documents\Programador\Projeto Ilya\Alto Comando\Salão de Conferência.md"

with open(filepath, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Delete lines at index 1630 and 1631 (0-indexed)
del lines[1630:1632]

with open(filepath, 'w', encoding='utf-8') as f:
    f.writelines(lines)

print("Linhas deletadas com sucesso!")
