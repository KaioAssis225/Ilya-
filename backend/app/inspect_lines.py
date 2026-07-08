filepath = r"C:\Users\matheus.cardoso\Documents\Programador\Projeto Ilya\Alto Comando\Salão de Conferência.md"

with open(filepath, 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i in range(1628, 1636):
    if i < len(lines):
        print(f"{i}: {repr(lines[i])}")
