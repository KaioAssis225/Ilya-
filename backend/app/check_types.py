import csv
from collections import Counter

csv_path = r"C:\Users\matheus.cardoso\Documents\Subir\Produtos.csv"

with open(csv_path, mode='r', encoding='utf-8-sig') as f:
    delimiter = ';'
    reader = csv.DictReader(f, delimiter=delimiter)
    types = Counter()
    for row in reader:
        row = {k.strip() if k else "": v.strip() if v else "" for k, v in row.items()}
        types[row.get('type')] += 1
            
    print("Tipos de produtos no CSV:")
    for t, count in types.items():
        print(f"Tipo: '{t}' | Quantidade: {count}")
