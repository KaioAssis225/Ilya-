csv_path = r"C:\Users\matheus.cardoso\Documents\Subir\Produtos.csv"

with open(csv_path, mode='r', encoding='utf-8-sig') as f:
    text = f.read()
    sample = text[:4096]
    semicolons = sample.count(";")
    commas = sample.count(",")
    print(f"No sample de 4096 caracteres:")
    print(f"Ponto e vírgulas (;): {semicolons}")
    print(f"Vírgulas (,): {commas}")
    delimiter = ";" if semicolons > commas else ","
    print(f"Delimitador detectado: '{delimiter}'")
