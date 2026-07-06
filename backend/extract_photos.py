import os
import sys
import zipfile
import shutil
import xml.etree.ElementTree as ET

xlsx_path = r"C:\Users\matheus.cardoso\Downloads\- TABELA ILYA - 26.06.2026.xlsx"
output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app", "static", "uploads")

# Garantir que a pasta de destino existe
os.makedirs(output_dir, exist_ok=True)

def sanitize_filename(filename):
    """Substitui caracteres inválidos do Windows por sublinhado."""
    invalid_chars = ['<', '>', ':', '"', '/', '\\', '|', '?', '*']
    sanitized = filename
    for char in invalid_chars:
        sanitized = sanitized.replace(char, '_')
    return sanitized.strip()

def get_shared_strings(zip_file):
    try:
        with zip_file.open("xl/sharedStrings.xml") as f:
            tree = ET.parse(f)
            root = tree.getroot()
            ns = {'ns': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
            strings = []
            for t in root.findall(".//ns:t", ns):
                strings.append(t.text if t.text else "")
            return strings
    except KeyError:
        return []

def get_sheet_file(zip_file, target_sheet_name):
    try:
        with zip_file.open("xl/workbook.xml") as f:
            tree = ET.parse(f)
            root = tree.getroot()
            ns = {'ns': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
            r_id = None
            for s in root.findall(".//ns:sheet", ns):
                if s.get("name").lower() == target_sheet_name.lower():
                    r_id = s.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
                    break
        if not r_id:
            return None
        with zip_file.open("xl/_rels/workbook.xml.rels") as f:
            tree = ET.parse(f)
            root = tree.getroot()
            ns = {'ns': 'http://schemas.openxmlformats.org/package/2006/relationships'}
            for rel in root.findall("ns:Relationship", ns):
                if rel.get("Id") == r_id:
                    target = rel.get("Target")
                    return f"xl/{target}" if not target.startswith("xl/") else target
        return None
    except Exception as e:
        print(f"Erro ao obter path da sheet: {e}")
        return None

def get_metadata_bks(zip_file):
    try:
        with zip_file.open("xl/metadata.xml") as f:
            tree = ET.parse(f)
            root = tree.getroot()
            ns = {'ns': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
            valueMetadata = root.find("ns:valueMetadata", ns)
            if valueMetadata is not None:
                return valueMetadata.findall("ns:bk", ns)
        return []
    except Exception as e:
        print(f"Erro ao ler metadata.xml: {e}")
        return []

def get_rich_values(zip_file):
    try:
        with zip_file.open("xl/richData/rdrichvalue.xml") as f:
            tree = ET.parse(f)
            root = tree.getroot()
            ns = {'ns': 'http://schemas.microsoft.com/office/spreadsheetml/2017/richdata'}
            return root.findall(".//ns:rv", ns)
    except Exception as e:
        print(f"Erro ao ler rdrichvalue.xml: {e}")
        return []

def get_rich_value_rels(zip_file):
    try:
        with zip_file.open("xl/richData/richValueRel.xml") as f:
            tree = ET.parse(f)
            root = tree.getroot()
            ns = {'ns': 'http://schemas.microsoft.com/office/spreadsheetml/2022/richvaluerel'}
            return root.findall(".//ns:rel", ns)
    except Exception as e:
        print(f"Erro ao ler richValueRel.xml: {e}")
        return []

def get_rich_value_rels_map(zip_file):
    try:
        with zip_file.open("xl/richData/_rels/richValueRel.xml.rels") as f:
            tree = ET.parse(f)
            root = tree.getroot()
            ns = {'ns': 'http://schemas.openxmlformats.org/package/2006/relationships'}
            rel_map = {}
            for rel in root.findall("ns:Relationship", ns):
                r_id = rel.get("Id")
                target = rel.get("Target")
                normalized = os.path.normpath(os.path.join("xl/richData", target)).replace("\\", "/")
                rel_map[r_id] = normalized
            return rel_map
    except Exception as e:
        print(f"Erro ao ler richValueRel.xml.rels: {e}")
        return {}

def parse_sheet_skus_and_vms(zip_file, sheet_path, shared_strings):
    try:
        with zip_file.open(sheet_path) as f:
            tree = ET.parse(f)
            root = tree.getroot()
            ns = {'ns': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
            row_skus = {}
            row_vms = {}
            for row in root.findall(".//ns:row", ns):
                r_idx = int(row.get("r")) - 1
                for cell in row.findall("ns:c", ns):
                    ref = cell.get("r")
                    col_letter = "".join([char for char in ref if char.isalpha()])
                    cell_type = cell.get("t")
                    val_node = cell.find("ns:v", ns)
                    val = val_node.text if val_node is not None else ""
                    if cell_type == "s" and val != "":
                        try:
                            val = shared_strings[int(val)]
                        except (ValueError, IndexError):
                            pass
                    if col_letter == "A":
                        sku = str(val).strip()
                        if sku:
                            row_skus[r_idx] = sku
                    elif col_letter == "B":
                        vm = cell.get("vm")
                        if vm:
                            row_vms[r_idx] = int(vm)
            return row_skus, row_vms
    except Exception as e:
        print(f"Erro ao ler sheet: {e}")
        return {}, {}

def run_extraction():
    saved = {}
    if not os.path.exists(xlsx_path):
        print(f"Erro: O arquivo {xlsx_path} nao foi encontrado.")
        return saved
        
    print(f"Carregando e processando planilha: {xlsx_path}")
    print(f"Diretório de destino: {output_dir}")
    
    try:
        with zipfile.ZipFile(xlsx_path, 'r') as zip_ref:
            shared_strings = get_shared_strings(zip_ref)
            sheet_path = get_sheet_file(zip_ref, "Foto")
            if not sheet_path:
                print("Erro: A sheet 'Foto' nao foi encontrada no arquivo Excel.")
                return saved
                
            metadata_bks = get_metadata_bks(zip_ref)
            rich_values = get_rich_values(zip_ref)
            rich_value_rels = get_rich_value_rels(zip_ref)
            rich_rels_map = get_rich_value_rels_map(zip_ref)
            
            row_skus, row_vms = parse_sheet_skus_and_vms(zip_ref, sheet_path, shared_strings)
            extracted_count = 0
            
            for row, vm in sorted(row_vms.items()):
                sku = row_skus.get(row)
                if not sku:
                    continue
                bk_idx = vm - 1
                if bk_idx >= len(metadata_bks):
                    continue
                bk = metadata_bks[bk_idx]
                rc = bk.find("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}rc")
                if rc is None:
                    continue
                v_val = int(rc.get("v"))
                if v_val >= len(rich_values):
                    continue
                rv = rich_values[v_val]
                v_elements = rv.findall("{http://schemas.microsoft.com/office/spreadsheetml/2017/richdata}v")
                if not v_elements:
                    continue
                rel_idx = int(v_elements[0].text)
                if rel_idx >= len(rich_value_rels):
                    continue
                rel = rich_value_rels[rel_idx]
                r_id = rel.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
                img_zip_path = rich_rels_map.get(r_id)
                if not img_zip_path:
                    continue
                _, ext = os.path.splitext(img_zip_path)
                if not ext:
                    ext = ".png"
                clean_sku = sanitize_filename(sku)
                dest_filename = f"{clean_sku}{ext.lower()}"
                dest_path = os.path.join(output_dir, dest_filename)
                
                try:
                    with zip_ref.open(img_zip_path) as src_file:
                        with open(dest_path, "wb") as dest_file:
                            shutil.copyfileobj(src_file, dest_file)
                    print(f"Extraído: Célula B{row+1} (SKU: {sku}) -> {dest_filename}")
                    saved[sku] = f"app/static/uploads/{dest_filename}"
                    extracted_count += 1
                except Exception as e:
                    print(f"Erro ao salvar foto de {sku}: {e}")
            print(f"\nExtração finalizada com sucesso! Total de fotos extraídas: {extracted_count}")
    except Exception as e:
        print(f"Erro no processamento do ZIP: {e}")
    return saved


def associate_db(saved):
    """Aponta o photo_path dos produtos existentes para a imagem extraída (Bloco 65).
    photo_path fica como 'app/static/uploads/{SKU}.ext', que o backend serve em
    '/static/uploads/{SKU}.ext'."""
    import asyncio
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from sqlalchemy import select
    from app.db.session import AsyncSessionLocal
    from app.models.product import Product

    async def _run():
        updated = 0
        async with AsyncSessionLocal() as db:
            for sku, path in saved.items():
                product = (await db.execute(
                    select(Product).where(Product.product_code == sku)
                )).scalar_one_or_none()
                if product:
                    product.photo_path = path
                    updated += 1
            await db.commit()
        return updated

    return asyncio.run(_run())


if __name__ == "__main__":
    # Permite informar o .xlsx por argumento; senão usa o caminho padrão acima.
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        xlsx_path = sys.argv[1]
    saved = run_extraction()
    if saved and "--no-db" not in sys.argv:
        try:
            updated = associate_db(saved)
            print(f"Produtos associados no banco: {updated}/{len(saved)}")
        except Exception as e:
            print(f"[aviso] Extração concluída, mas a associação no banco falhou: {e}")
