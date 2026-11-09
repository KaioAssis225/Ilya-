"""Importa a planilha do TECIDO FORNECIDO (Portugal) pela rota oficial da API.

Le o arquivo da fabrica (.xlsx ou .csv) com as colunas COD, PVP, LOJISTA,
ARQUITETO, CORPORATIVO e MTS TECIDO e envia para
`POST /markets/EU/supplied-fabric/import`.

  * Sem `--apply` e so SIMULACAO (dry-run): a API diz o que seria criado,
    atualizado ou ignorado e NADA e gravado.
  * Com `--apply` grava de verdade (pede para digitar IMPORTAR).
  * Precisa de conta de plataforma (platform_admin). A senha e pedida no
    terminal (`getpass`); nao existe parametro para ela.
  * Precos sao arredondados pela API (2 casas, ROUND_HALF_UP). Codigo que nao
    existe no EU nao e erro: aparece no relatorio como "ignorado".
  * Nao precisa de nenhuma biblioteca alem do `httpx` que o script de fotos ja
    usa: o .xlsx e lido com a biblioteca padrao do Python.

Uso:
  py ops/importar_tecido_fornecido.py "C:\\caminho\\Sem tecido ofc.xlsx"
  py ops/importar_tecido_fornecido.py "C:\\caminho\\Sem tecido ofc.xlsx" --apply
"""
from __future__ import annotations

import argparse
import csv
import getpass
import io
import os
import re
import sys
import zipfile
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Callable
from xml.etree import ElementTree

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from trocar_fotos_eu import (  # noqa: E402
    BASE_URL_PLATAFORMA,
    ORIGEM_PADRAO,
    ErroFatal,
    Sessao,
    _detalhe,
    autenticar,
    renovar_token,
)

CONFIRMACAO = "IMPORTAR"
COLUNAS = ["COD", "PVP", "LOJISTA", "ARQUITETO", "CORPORATIVO", "MTS TECIDO"]
_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


# --------------------------------------------------------------------------- #
# Leitura do arquivo (.xlsx sem dependencias, ou .csv)
# --------------------------------------------------------------------------- #

def _indice_coluna(referencia: str) -> int:
    letras = re.match(r"[A-Z]+", referencia).group(0)  # type: ignore[union-attr]
    indice = 0
    for letra in letras:
        indice = indice * 26 + ord(letra) - 64
    return indice - 1


def _numero_como_o_excel(texto: str) -> str:
    """O .xlsx guarda 17 digitos (4283.2349999999997); o Excel mostra 15 (4283.235).
    Usa os 15, que e o valor que a pessoa ve na planilha, antes de arredondar."""
    try:
        return format(Decimal(format(float(texto), ".15g")), "f")
    except (ValueError, ArithmeticError):
        return texto


def ler_xlsx(caminho: Path) -> list[list[str]]:
    """Primeira aba do .xlsx como lista de linhas de texto (valores ja calculados)."""
    with zipfile.ZipFile(caminho) as pacote:
        textos: list[str] = []
        if "xl/sharedStrings.xml" in pacote.namelist():
            raiz = ElementTree.fromstring(pacote.read("xl/sharedStrings.xml"))
            textos = ["".join(t.text or "" for t in si.iter(f"{{{_NS['m']}}}t")) for si in raiz]
        planilhas = sorted(n for n in pacote.namelist() if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n))
        if not planilhas:
            raise ErroFatal("O arquivo .xlsx nao tem nenhuma aba.")
        raiz = ElementTree.fromstring(pacote.read(planilhas[0]))
    linhas: list[list[str]] = []
    for linha in raiz.iter(f"{{{_NS['m']}}}row"):
        valores: dict[int, str] = {}
        for celula in linha.iter(f"{{{_NS['m']}}}c"):
            tipo = celula.get("t")
            valor = celula.find("m:v", _NS)
            if tipo == "inlineStr":
                texto = "".join(t.text or "" for t in celula.iter(f"{{{_NS['m']}}}t"))
            elif valor is None or valor.text is None:
                continue
            elif tipo == "s":
                texto = textos[int(valor.text)]
            elif tipo in (None, "n"):
                texto = _numero_como_o_excel(valor.text)
            else:
                texto = valor.text
            valores[_indice_coluna(celula.get("r", "A1"))] = texto
        if valores:
            linhas.append([valores.get(i, "") for i in range(max(valores) + 1)])
    return linhas


def ler_arquivo(caminho: Path) -> list[list[str]]:
    if not caminho.is_file():
        raise ErroFatal(f"Arquivo nao encontrado: {caminho}")
    if caminho.suffix.lower() == ".xlsx":
        return ler_xlsx(caminho)
    if caminho.suffix.lower() == ".csv":
        texto = caminho.read_text(encoding="utf-8-sig")
        primeira = texto.splitlines()[0] if texto.strip() else ""
        delimitador = ";" if primeira.count(";") >= primeira.count(",") else ","
        return [linha for linha in csv.reader(io.StringIO(texto), delimiter=delimitador)]
    raise ErroFatal("Use um arquivo .xlsx ou .csv.")


def montar_csv(linhas: list[list[str]]) -> tuple[bytes, int]:
    """CSV (`;`) com o cabecalho da planilha. Devolve (conteudo, linhas de dados)."""
    if not linhas:
        raise ErroFatal("A planilha esta vazia.")
    cabecalho = [c.strip().upper() for c in linhas[0]]
    faltando = [c for c in COLUNAS if c not in cabecalho]
    if faltando:
        raise ErroFatal(f"Faltam colunas na planilha: {', '.join(faltando)}.")
    posicao = {nome: cabecalho.index(nome) for nome in COLUNAS}
    saida = io.StringIO()
    escritor = csv.writer(saida, delimiter=";", lineterminator="\n")
    escritor.writerow(COLUNAS)
    dados = 0
    for linha in linhas[1:]:
        celulas = [(linha[posicao[n]] if posicao[n] < len(linha) else "").strip() for n in COLUNAS]
        if not any(celulas):
            continue
        escritor.writerow(celulas)
        dados += 1
    return saida.getvalue().encode("utf-8"), dados


# --------------------------------------------------------------------------- #
# Chamada da API e relatorio
# --------------------------------------------------------------------------- #

def enviar(sessao: Sessao, conteudo: bytes, *, aplicar: bool) -> dict:
    for tentativa in range(2):
        resposta = sessao.client.post(
            sessao.url("/markets/EU/supplied-fabric/import"),
            params={"dry_run": "false" if aplicar else "true"},
            files={"file": ("tecido-fornecido.csv", conteudo, "text/csv")},
            headers=sessao.cabecalho(),
            timeout=300.0,
        )
        if resposta.status_code == 401 and tentativa == 0 and renovar_token(sessao):
            continue
        break
    if resposta.status_code == 422:
        try:
            detalhe = resposta.json().get("detail", {})
            lista = detalhe.get("errors") if isinstance(detalhe, dict) else None
        except Exception:  # noqa: BLE001
            lista = None
        raise ErroFatal("A API recusou o arquivo (nada foi alterado):\n  - " + "\n  - ".join(lista or [_detalhe(resposta)]))
    if resposta.status_code != 200:
        raise ErroFatal(f"A API respondeu erro: {_detalhe(resposta)}")
    return resposta.json()


def salvar_relatorio(caminho: Path, resultado: dict) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", newline="", encoding="utf-8-sig") as arquivo:
        escritor = csv.writer(arquivo, delimiter=";")
        escritor.writerow(["codigo", "situacao", "detalhe"])
        for sku in resultado["to_create"]:
            escritor.writerow([sku, "CRIAR", ""])
        for item in resultado["to_update"]:
            mudancas = "; ".join(f"{campo}: {v['from']} -> {v['to']}" for campo, v in item["changes"].items())
            escritor.writerow([item["sku"], "ATUALIZAR", mudancas])
        for sku in resultado["unchanged"]:
            escritor.writerow([sku, "SEM_MUDANCA", ""])
        for sku in resultado["unknown_skus"]:
            escritor.writerow([sku, "IGNORADO_NAO_EXISTE_NO_EU", "Codigo nao cadastrado no mercado EU."])
        for sku in resultado["fabric_via_legacy_selector"]:
            escritor.writerow([sku, "OK_SELETOR_ANTIGO", "Tem TECIDOS_IBTW no seletor antigo: a opcao aparece."])
        for sku in resultado["without_fabric_category"]:
            escritor.writerow([sku, "AVISO_SEM_TECIDOS_IBTW", "Sem TECIDOS_IBTW em aplicacao nem no seletor antigo: a opcao nao aparece ate o produto ter essa categoria."])


def texto_resumo(resultado: dict) -> str:
    return "\n".join([
        f"Linhas no arquivo:                            {resultado['rows_in_file']}",
        f"Vao ser CRIADOS:                              {len(resultado['to_create'])}",
        f"Vao ser ATUALIZADOS:                          {len(resultado['to_update'])}",
        f"Sem mudanca:                                  {len(resultado['unchanged'])}",
        f"IGNORADOS (codigo nao existe no EU):          {len(resultado['unknown_skus'])}",
        f"Com TECIDOS_IBTW em aplicacao (opcao aparece): {len(resultado['fabric_via_application'])}",
        f"Com TECIDOS_IBTW no seletor antigo (aparece):   {len(resultado['fabric_via_legacy_selector'])}",
        f"AVISO (sem TECIDOS_IBTW em nenhum dos dois):    {len(resultado['without_fabric_category'])}",
    ])


def main(
    argv: list[str] | None = None,
    *,
    client: httpx.Client | None = None,
    entrada: Callable[[str], str] = input,
    senha: Callable[[str], str] = getpass.getpass,
    imprimir: Callable[[str], None] = print,
    ambiente: dict | None = None,
) -> int:
    raiz = Path(__file__).resolve().parent.parent
    p = argparse.ArgumentParser(description="Importa preco sem tecido e metragem (TECIDO FORNECIDO) do EU.")
    p.add_argument("arquivo", type=Path, help="Planilha .xlsx ou .csv da fabrica")
    p.add_argument("--apply", action="store_true", help="Grava de verdade. Sem isso e so simulacao (dry-run).")
    p.add_argument("--sim", action="store_true", help="Com --apply, nao pergunta a confirmacao digitada.")
    p.add_argument("--base-url", default=os.environ.get("ILYA_API_URL", BASE_URL_PLATAFORMA))
    p.add_argument("--origin", default=ORIGEM_PADRAO)
    p.add_argument("--saida", type=Path, default=raiz / "logs" / "tecido-fornecido",
                   help="Pasta dos relatorios (padrao: logs/tecido-fornecido, fora do git).")
    args = p.parse_args(argv)
    ambiente = os.environ if ambiente is None else ambiente
    carimbo = datetime.now().strftime("%Y%m%d-%H%M%S")
    proprio_client = client is None
    if client is None:
        client = httpx.Client(timeout=30.0, follow_redirects=False)
    client.headers.update({"Origin": args.origin})
    sessao = Sessao(client=client, base_url=args.base_url, plataforma=True)
    try:
        conteudo, dados = montar_csv(ler_arquivo(args.arquivo))
        imprimir(f"Modo: {'APLICAR (grava no site)' if args.apply else 'DRY-RUN (nao grava nada)'}")
        imprimir(f"Linhas de dados lidas na planilha: {dados}")
        autenticar(
            sessao,
            token_env=ambiente.get("ILYA_TOKEN"),
            pedir_usuario=lambda: entrada("Usuario ou e-mail (conta de plataforma): "),
            pedir_senha=lambda: senha("Senha (nao aparece ao digitar): "),
        )
        # Sempre simula primeiro; so grava depois de mostrar o resumo e confirmar.
        simulacao = enviar(sessao, conteudo, aplicar=False)
        relatorio = args.saida / f"relatorio-dry-run-{carimbo}.csv"
        salvar_relatorio(relatorio, simulacao)
        imprimir("\n" + texto_resumo(simulacao))
        imprimir(f"\nRelatorio: {relatorio}")
        if not args.apply:
            imprimir("\nNada foi gravado. Para gravar de verdade rode de novo com --apply.")
            return 0
        if not (simulacao["to_create"] or simulacao["to_update"]):
            imprimir("\nNao ha nada para gravar.")
            return 0
        if not args.sim and entrada(
            f"\nVai gravar {len(simulacao['to_create'])} novos e atualizar {len(simulacao['to_update'])}. "
            f"Digite {CONFIRMACAO} para continuar: "
        ).strip() != CONFIRMACAO:
            imprimir("Cancelado. Nada foi gravado.")
            return 1
        resultado = enviar(sessao, conteudo, aplicar=True)
        aplicado = args.saida / f"relatorio-apply-{carimbo}.csv"
        salvar_relatorio(aplicado, resultado)
        imprimir(f"\nGravado: {resultado['applied']} produtos.\nRelatorio: {aplicado}")
        return 0
    except ErroFatal as erro:
        imprimir(f"\nERRO: {erro}")
        return 1
    except httpx.HTTPError as erro:
        imprimir(f"\nERRO de rede: {type(erro).__name__}. Confira se algo foi gravado rodando a simulacao de novo.")
        return 1
    finally:
        if proprio_client:
            client.close()


if __name__ == "__main__":
    sys.exit(main())
