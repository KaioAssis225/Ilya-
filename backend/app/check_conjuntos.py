import csv

csv_path = r"C:\Users\matheus.cardoso\Documents\Subir\Produtos.csv"

with open(csv_path, mode='r', encoding='utf-8-sig') as f:
    delimiter = ';'
    reader = csv.DictReader(f, delimiter=delimiter)
    conjuntos = []
    for row in reader:
        row = {k.strip() if k else "": v.strip() if v else "" for k, v in row.items()}
        if row.get('type') == 'Conjunto':
            conjuntos.append(row)
            
    print(f"Encontrados {len(conjuntos)} conjuntos no CSV:")
    for c in conjuntos[:10]:
        print(f"SKU: {c['product_code']} | Desc: {c['description']} | Lojista: {c['price_lojista']} | Corp: {c['price_corporativo']}")
