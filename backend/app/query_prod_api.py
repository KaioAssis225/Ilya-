import urllib.request
import json

base_url = "https://ilya-production-7857.up.railway.app/api/v1"
admin_email = "admin@ilya.com"
admin_password = "Ilya@2025!"  # Senha padrão do seed do admin

def get_token():
    url = f"{base_url}/auth/login"
    data = json.dumps({
        "identifier": admin_email,
        "password": admin_password
    }).encode("utf-8")
    
    req = urllib.request.Request(url, data=data, headers={
        "Content-Type": "application/json"
    })
    
    try:
        with urllib.request.urlopen(req) as res:
            resp_data = json.loads(res.read().decode())
            return resp_data.get("access_token")
    except Exception as e:
        print(f"Erro ao obter token do ambiente de produção: {e}")
        return None

def list_products(token):
    url = f"{base_url}/products?limit=200"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}"
    })
    
    try:
        with urllib.request.urlopen(req) as res:
            return json.loads(res.read().decode())
    except Exception as e:
        print(f"Erro ao obter produtos de produção: {e}")
        return []

def main():
    token = get_token()
    if not token:
        return
    print("Autenticado com sucesso na produção!")
    
    products = list_products(token)
    print(f"Obtidos {len(products)} produtos da produção:")
    for p in products[:15]:
        print(f"SKU: {p['product_code']} | Lojista: {p['price_lojista']} | Corp: {p['price_corporativo']} | Price: {p['price']}")

if __name__ == "__main__":
    main()
