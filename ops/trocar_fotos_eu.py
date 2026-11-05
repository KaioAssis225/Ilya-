#!/usr/bin/env python3
"""Troca as fotos dos produtos do mercado EU (Portugal) por arquivos de uma pasta.

Cada arquivo da pasta se chama `<CODIGO>.jpeg` (o nome sem a extensao e o
`product_code`). So mexe em produto que existe no site EU; o resto e ignorado.

Dois modos:
  * Padrao (DRY-RUN): le a pasta, le os produtos EU no site e gera um relatorio.
    NAO altera nada no site (so faz login e GET).
  * `--apply`: para cada produto "VAI_TROCAR", chama a rota oficial da API
    (`POST /products/{id}/upload-photo`), um por vez. A propria API apaga a foto
    antiga do bucket europeu depois de gravar a nova. Foto que o produto
    "empresta" do catalogo do Brasil NAO e apagada (a API protege o bucket BR).

Seguranca:
  * A senha e pedida no terminal (`getpass`); nao existe parametro para ela.
  * Alternativa: defina a variavel de ambiente `ILYA_TOKEN` com um token ja
    emitido para o mercado EU. O token nunca e impresso nem gravado.
  * Nenhuma credencial de bucket passa por aqui: o upload vai pela API.

Uso (troca de fotos):
  py ops/trocar_fotos_eu.py "C:\\Users\\...\\IBTW"             # dry-run
  py ops/trocar_fotos_eu.py "C:\\Users\\...\\IBTW" --apply     # troca de verdade

Fotos orfas do bucket EU (objetos que nenhuma linha do banco usa), DEPOIS da troca.
Exige conta de plataforma (platform_admin). Nada e apagado de imediato: as orfas
vao para a quarentena `eu-trash/<data>/` do mesmo bucket e podem ser restauradas.
  py ops/trocar_fotos_eu.py --orfas                                  # so lista
  py ops/trocar_fotos_eu.py --orfas --apagar                         # move p/ quarentena
  py ops/trocar_fotos_eu.py --orfas --quarentena                     # ver lotes
  py ops/trocar_fotos_eu.py --orfas --restaurar AAAA-MM-DD           # desfaz
  py ops/trocar_fotos_eu.py --orfas --esvaziar-quarentena AAAA-MM-DD # apaga de vez (7+ dias)
"""

from __future__ import annotations

import argparse
import base64
import csv
import getpass
import json
import mimetypes
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable
from urllib.parse import unquote, urlsplit

import httpx

BASE_URL_PADRAO = "https://ilya-rust.vercel.app/api/v1"
# Mesma API publicada em ops/sincronizar-fotos-eu.ps1. Os passos de orfas fazem
# chamadas longas (varredura do banco + bucket), melhor sem o proxy da Vercel.
BASE_URL_PLATAFORMA = "https://ilya-production-7857.up.railway.app/api/v1"
ORIGEM_PADRAO = "https://ilya-rust.vercel.app"
EXTENSOES_IMAGEM = {".jpeg", ".jpg", ".png", ".webp"}
PREFIXO_MEDIA = "/api/v1/media/"
PAGINA = 500
CONFIRMACAO = "TROCAR"

# Status do plano (dry-run) e do resultado (apply).
VAI_TROCAR = "VAI_TROCAR"
SEM_PRODUTO = "SEM_PRODUTO_NO_SITE"
CODIGO_DUPLICADO = "CODIGO_DUPLICADO_NO_SITE"
ARQUIVO_DUPLICADO = "ARQUIVO_DUPLICADO"
OK = "OK"
COMPARTILHADO_BR = "COMPARTILHADO_COM_BR"
ERRO = "ERRO"
NAO_TENTADO = "NAO_TENTADO"

MOTIVOS = {
    VAI_TROCAR: "Produto ativo no site EU; a foto sera trocada no --apply.",
    SEM_PRODUTO: (
        "Nao aparece no catalogo EU ativo (nao existe, esta inativo, "
        "indisponivel ou oculto). Pulado."
    ),
    CODIGO_DUPLICADO: "Mais de um produto EU com esse codigo. Pulado por seguranca.",
    ARQUIVO_DUPLICADO: "Mais de um arquivo na pasta para esse codigo. Pulado.",
}


class ErroFatal(Exception):
    """Erro que impede a execucao (login, mercado, rede). Mensagem em portugues."""


@dataclass
class Linha:
    codigo: str
    arquivo: Path | None
    status: str
    motivo: str = ""
    product_id: str = ""
    foto_antiga: str = ""
    origem_foto_antiga: str = ""


@dataclass
class Sessao:
    client: httpx.Client
    base_url: str
    token: str = ""
    pode_renovar: bool = False
    plataforma: bool = False  # True nos passos de fotos orfas (login de plataforma)

    def url(self, caminho: str) -> str:
        return self.base_url.rstrip("/") + caminho

    def cabecalho(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"}


# --------------------------------------------------------------------------- #
# Pasta de fotos
# --------------------------------------------------------------------------- #

def normalizar_codigo(codigo: str) -> str:
    return codigo.strip().upper()


def listar_arquivos(pasta: Path) -> tuple[dict[str, list[Path]], list[str]]:
    """Devolve {codigo normalizado: [arquivos]} e a lista de arquivos ignorados."""
    if not pasta.is_dir():
        raise ErroFatal(f"A pasta nao existe: {pasta}")
    por_codigo: dict[str, list[Path]] = {}
    ignorados: list[str] = []
    for caminho in sorted(pasta.iterdir(), key=lambda p: p.name.lower()):
        if not caminho.is_file() or caminho.suffix.lower() not in EXTENSOES_IMAGEM:
            ignorados.append(caminho.name)
            continue
        codigo = normalizar_codigo(caminho.stem)
        if not codigo:
            ignorados.append(caminho.name)
            continue
        por_codigo.setdefault(codigo, []).append(caminho)
    return por_codigo, ignorados


# --------------------------------------------------------------------------- #
# Foto atual (chave do objeto no bucket)
# --------------------------------------------------------------------------- #

def extrair_chave(photo_url: str | None) -> str:
    """`/api/v1/media/eu-products/abc.webp?expires=..` -> `eu-products/abc.webp`."""
    if not photo_url:
        return ""
    caminho = urlsplit(photo_url).path
    indice = caminho.find(PREFIXO_MEDIA)
    if indice < 0:
        return ""
    return unquote(caminho[indice + len(PREFIXO_MEDIA):])


def origem_da_chave(chave: str) -> str:
    if not chave:
        return "sem foto"
    if chave.startswith("eu-"):
        return "bucket EU (sera apagada na troca)"
    return "bucket BR/herdada (NAO sera apagada; pode dar 403)"


# --------------------------------------------------------------------------- #
# Autenticacao
# --------------------------------------------------------------------------- #

def _claims_do_token(token: str) -> dict:
    """Le o corpo do JWT SEM validar assinatura (so para saber o mercado)."""
    try:
        corpo = token.split(".")[1]
        corpo += "=" * (-len(corpo) % 4)
        return json.loads(base64.urlsafe_b64decode(corpo))
    except Exception:  # noqa: BLE001 - token malformado
        return {}


def _detalhe(resposta: httpx.Response) -> str:
    try:
        detalhe = resposta.json().get("detail")
    except Exception:  # noqa: BLE001
        detalhe = None
    return str(detalhe)[:300] if detalhe else f"HTTP {resposta.status_code}"


def _token_de_plataforma(token: str) -> bool:
    claims = _claims_do_token(token)
    return claims.get("scope") == "platform" and "market" not in claims


def autenticar(
    sessao: Sessao,
    *,
    token_env: str | None,
    pedir_usuario: Callable[[], str],
    pedir_senha: Callable[[], str],
) -> None:
    """Deixa `sessao.token` pronto: mercado EU (fotos) ou plataforma (orfas).
    Nunca imprime segredos."""
    if token_env:
        sessao.token = token_env.strip()
        sessao.pode_renovar = False
        if sessao.plataforma:
            if not _token_de_plataforma(sessao.token):
                raise ErroFatal(
                    "O token em ILYA_TOKEN nao e de plataforma. Para as fotos orfas "
                    "use a sessao de plataforma, ou rode sem ILYA_TOKEN para digitar "
                    "usuario e senha."
                )
        elif _claims_do_token(sessao.token).get("market") != "EU":
            raise ErroFatal(
                "O token em ILYA_TOKEN nao e do mercado EU. Gere o token com o "
                "sistema em Portugal, ou rode sem ILYA_TOKEN para digitar "
                "usuario e senha."
            )
        return

    identificador = pedir_usuario().strip()
    senha = pedir_senha()
    if not identificador or not senha:
        raise ErroFatal("Usuario e senha sao obrigatorios.")
    resposta = sessao.client.post(
        sessao.url("/platform/auth/login" if sessao.plataforma else "/auth/login"),
        json={"identifier": identificador, "password": senha},
    )
    del senha
    if resposta.status_code == 403 and sessao.plataforma:
        raise ErroFatal("Essa conta nao tem permissao de plataforma (platform_admin).")
    if resposta.status_code != 200:
        raise ErroFatal(f"Login recusado: {_detalhe(resposta)}")
    sessao.token = resposta.json()["access_token"]
    sessao.pode_renovar = True

    if sessao.plataforma:
        if not _token_de_plataforma(sessao.token):
            raise ErroFatal("A sessao nao ficou no escopo de plataforma. Nada foi alterado.")
        return
    if _claims_do_token(sessao.token).get("market") != "EU":
        troca = sessao.client.post(
            sessao.url("/auth/switch-market"),
            json={"market": "EU"},
            headers=sessao.cabecalho(),
        )
        if troca.status_code != 200:
            raise ErroFatal(
                f"Nao consegui trocar para o mercado EU: {_detalhe(troca)}"
            )
        sessao.token = troca.json()["access_token"]
    if _claims_do_token(sessao.token).get("market") != "EU":
        raise ErroFatal("A sessao nao ficou no mercado EU. Nada foi alterado.")


def renovar_token(sessao: Sessao) -> bool:
    """Renova o access token pelo cookie de refresh. Falso se nao for possivel."""
    if not sessao.pode_renovar:
        return False
    resposta = sessao.client.post(
        sessao.url("/platform/auth/refresh" if sessao.plataforma else "/auth/refresh")
    )
    if resposta.status_code != 200:
        return False
    novo = resposta.json().get("access_token")
    if not novo:
        return False
    if sessao.plataforma:
        if not _token_de_plataforma(novo):
            return False
    elif _claims_do_token(novo).get("market") != "EU":
        return False
    sessao.token = novo
    return True


# --------------------------------------------------------------------------- #
# Leitura dos produtos EU (somente GET)
# --------------------------------------------------------------------------- #

def buscar_produtos_eu(sessao: Sessao) -> list[dict]:
    produtos: list[dict] = []
    pulo = 0
    renovou = False
    while True:
        resposta = sessao.client.get(
            sessao.url("/products"),
            params={
                "skip": pulo,
                "limit": PAGINA,
                "include_total": "false",
                "sort_by": "product_code",
            },
            headers=sessao.cabecalho(),
        )
        if resposta.status_code == 401 and not renovou and renovar_token(sessao):
            renovou = True
            continue
        if resposta.status_code != 200:
            raise ErroFatal(f"Falha ao listar produtos EU: {_detalhe(resposta)}")
        renovou = False
        pagina = resposta.json()
        produtos.extend(pagina)
        if resposta.headers.get("X-Has-More", "false").lower() != "true" or not pagina:
            return produtos
        pulo += len(pagina)


# --------------------------------------------------------------------------- #
# Plano (dry-run)
# --------------------------------------------------------------------------- #

def montar_plano(
    arquivos: dict[str, list[Path]], produtos: list[dict]
) -> list[Linha]:
    por_codigo: dict[str, list[dict]] = {}
    for produto in produtos:
        codigo = normalizar_codigo(str(produto.get("product_code") or ""))
        if codigo:
            por_codigo.setdefault(codigo, []).append(produto)

    plano: list[Linha] = []
    for codigo in sorted(arquivos):
        caminhos = arquivos[codigo]
        achados = por_codigo.get(codigo, [])
        if len(caminhos) > 1:
            plano.append(Linha(codigo, None, ARQUIVO_DUPLICADO, MOTIVOS[ARQUIVO_DUPLICADO]))
        elif not achados:
            plano.append(Linha(codigo, caminhos[0], SEM_PRODUTO, MOTIVOS[SEM_PRODUTO]))
        elif len(achados) > 1:
            plano.append(Linha(codigo, caminhos[0], CODIGO_DUPLICADO, MOTIVOS[CODIGO_DUPLICADO]))
        else:
            produto = achados[0]
            chave = extrair_chave(produto.get("photo_url"))
            plano.append(Linha(
                codigo, caminhos[0], VAI_TROCAR, MOTIVOS[VAI_TROCAR],
                product_id=str(produto["id"]),
                foto_antiga=chave,
                origem_foto_antiga=origem_da_chave(chave),
            ))
    return plano


def resumir(plano: list[Linha], ignorados: list[str]) -> dict[str, int]:
    contagem: dict[str, int] = {}
    for linha in plano:
        contagem[linha.status] = contagem.get(linha.status, 0) + 1
    contagem["_arquivos_ignorados"] = len(ignorados)
    contagem["_total_arquivos"] = len(plano)
    return contagem


# --------------------------------------------------------------------------- #
# Arquivos de saida
# --------------------------------------------------------------------------- #

COLUNAS_RELATORIO = [
    "codigo", "arquivo", "status", "motivo", "product_id",
    "foto_atual_chave", "foto_atual_origem",
]
COLUNAS_BACKUP = ["product_code", "product_id", "foto_antiga_chave", "origem"]
COLUNAS_LOG = [
    "hora", "codigo", "status", "http", "foto_antiga_chave",
    "foto_nova_chave", "foto_antiga_apagada_pelo_servidor", "mensagem",
]


def _abrir_csv(caminho: Path):
    caminho.parent.mkdir(parents=True, exist_ok=True)
    return open(caminho, "w", newline="", encoding="utf-8-sig")


def salvar_relatorio(caminho: Path, plano: list[Linha]) -> None:
    with _abrir_csv(caminho) as arq:
        escritor = csv.writer(arq, delimiter=";")
        escritor.writerow(COLUNAS_RELATORIO)
        for l in plano:
            escritor.writerow([
                l.codigo, l.arquivo.name if l.arquivo else "", l.status, l.motivo,
                l.product_id, l.foto_antiga, l.origem_foto_antiga,
            ])


def salvar_backup(caminho: Path, produtos: list[dict], codigos: set[str]) -> int:
    """Lista `product_code -> foto antiga` dos produtos envolvidos. So referencia."""
    n = 0
    with _abrir_csv(caminho) as arq:
        escritor = csv.writer(arq, delimiter=";")
        escritor.writerow(COLUNAS_BACKUP)
        for produto in sorted(produtos, key=lambda p: str(p.get("product_code"))):
            codigo = normalizar_codigo(str(produto.get("product_code") or ""))
            if codigo not in codigos:
                continue
            chave = extrair_chave(produto.get("photo_url"))
            escritor.writerow([
                produto.get("product_code"), produto.get("id"), chave, origem_da_chave(chave),
            ])
            n += 1
    return n


def texto_resumo(contagem: dict[str, int], pasta: Path, modo: str) -> str:
    rotulos = [
        (VAI_TROCAR, "vai trocar"),
        (SEM_PRODUTO, "sem produto ativo no site EU (pula)"),
        (CODIGO_DUPLICADO, "codigo duplicado no site (pula)"),
        (ARQUIVO_DUPLICADO, "arquivo duplicado na pasta (pula)"),
    ]
    linhas = [
        f"Modo: {modo}",
        f"Pasta: {pasta}",
        f"Arquivos de foto lidos: {contagem['_total_arquivos']}",
    ]
    for status, rotulo in rotulos:
        linhas.append(f"  - {rotulo}: {contagem.get(status, 0)}")
    linhas.append(f"Arquivos ignorados (nao sao foto, ex.: Thumbs.db): {contagem['_arquivos_ignorados']}")
    linhas.append(
        "Obs.: 'compartilhado com o BR' so aparece na hora da troca (a API responde 403 "
        "e o script pula esse produto)."
    )
    return "\n".join(linhas)


# --------------------------------------------------------------------------- #
# Aplicacao (--apply)
# --------------------------------------------------------------------------- #

def _enviar_foto(sessao: Sessao, linha: Linha) -> httpx.Response:
    caminho = linha.arquivo
    tipo = mimetypes.guess_type(caminho.name)[0] or "image/jpeg"
    with open(caminho, "rb") as arq:
        conteudo = arq.read()
    return sessao.client.post(
        sessao.url(f"/products/{linha.product_id}/upload-photo"),
        files={"file": (caminho.name, conteudo, tipo)},
        headers=sessao.cabecalho(),
        timeout=60.0,
    )


def _enviar_com_tentativas(
    sessao: Sessao, linha: Linha, dormir: Callable[[float], None]
) -> httpx.Response:
    """Tenta de novo so quando a API certamente nao processou (429/503/sem conexao)
    ou quando o token venceu (401, uma renovacao). Nunca repete apos timeout de
    leitura, para nao gerar foto duplicada no bucket."""
    renovou = False
    tentativas = 0
    while True:
        try:
            resposta = _enviar_foto(sessao, linha)
        except (httpx.ConnectError, httpx.ConnectTimeout):
            tentativas += 1
            if tentativas > 2:
                raise
            dormir(3.0 * tentativas)
            continue
        if resposta.status_code == 401 and not renovou:
            renovou = True
            if renovar_token(sessao):
                continue
            raise ErroFatal(
                "A sessao venceu e nao foi possivel renovar. Rode o script de novo "
                "(ele pode ser repetido com seguranca)."
            )
        if resposta.status_code in (429, 503) and tentativas < 3:
            tentativas += 1
            espera = resposta.headers.get("Retry-After", "")
            dormir(float(espera) if espera.replace(".", "", 1).isdigit() else 5.0 * tentativas)
            continue
        return resposta


def aplicar(
    sessao: Sessao,
    plano: list[Linha],
    caminho_log: Path,
    *,
    pausa: float,
    dormir: Callable[[float], None] = time.sleep,
    agora: Callable[[], datetime] = datetime.now,
    imprimir: Callable[[str], None] = print,
) -> dict[str, int]:
    """Troca uma foto por vez; erro em uma nao para as outras. Grava o log a cada linha."""
    fila = [l for l in plano if l.status == VAI_TROCAR]
    contagem = {OK: 0, COMPARTILHADO_BR: 0, ERRO: 0, NAO_TENTADO: 0}
    with _abrir_csv(caminho_log) as arq:
        escritor = csv.writer(arq, delimiter=";")
        escritor.writerow(COLUNAS_LOG)

        def registrar(l: Linha, status: str, http: str, nova: str, apagada: str, msg: str) -> None:
            escritor.writerow([
                agora().isoformat(timespec="seconds"), l.codigo, status, http,
                l.foto_antiga, nova, apagada, msg,
            ])
            arq.flush()
            contagem[status] += 1

        for posicao, linha in enumerate(fila, start=1):
            apagaria = linha.foto_antiga.startswith("eu-")
            try:
                resposta = _enviar_com_tentativas(sessao, linha, dormir)
            except ErroFatal as erro:
                for restante in fila[posicao - 1:]:
                    registrar(restante, NAO_TENTADO, "", "", "", str(erro))
                imprimir(f"PAROU: {erro}")
                break
            except httpx.HTTPError as erro:
                registrar(linha, ERRO, "", "", "", f"Falha de rede: {type(erro).__name__}")
                imprimir(f"[{posicao}/{len(fila)}] {linha.codigo}: ERRO de rede")
                dormir(pausa)
                continue

            http = str(resposta.status_code)
            if resposta.status_code == 200:
                try:
                    nova = extrair_chave(resposta.json().get("photo_url"))
                except ValueError:
                    nova = ""
                if nova and nova != linha.foto_antiga:
                    registrar(linha, OK, http, nova, "sim, se nenhum outro item a usa" if apagaria else "nao (nao era do bucket EU)", "")
                    imprimir(f"[{posicao}/{len(fila)}] {linha.codigo}: ok")
                else:
                    registrar(linha, ERRO, http, nova, "", "API respondeu 200 mas a foto nao mudou; confira no site.")
                    imprimir(f"[{posicao}/{len(fila)}] {linha.codigo}: ERRO (foto nao mudou)")
            elif resposta.status_code == 403:
                registrar(linha, COMPARTILHADO_BR, http, "", "", _detalhe(resposta))
                imprimir(f"[{posicao}/{len(fila)}] {linha.codigo}: pulado (compartilhado com o BR)")
            else:
                registrar(linha, ERRO, http, "", "", _detalhe(resposta))
                imprimir(f"[{posicao}/{len(fila)}] {linha.codigo}: ERRO {http}")
            if posicao < len(fila):
                dormir(pausa)
    return contagem


# --------------------------------------------------------------------------- #
# Fotos orfas do bucket EU (rotas de plataforma; nada sai direto do bucket)
# --------------------------------------------------------------------------- #

CONFIRMACAO_ORFAS = "APAGAR"
CONFIRMACAO_DEFINITIVA = "APAGAR DE VEZ"
LOTE_ORFAS = 200
COLUNAS_LOG_ORFAS = ["hora", "acao", "chave", "status", "mensagem"]


def _chamar(sessao: Sessao, metodo: str, caminho: str, *, json_corpo: dict | None = None,
            espera: float = 300.0) -> httpx.Response:
    """Chamada de plataforma; renova o token uma vez se vencer."""
    for tentativa in range(2):
        resposta = sessao.client.request(
            metodo, sessao.url(caminho), json=json_corpo,
            headers=sessao.cabecalho(), timeout=espera,
        )
        if resposta.status_code == 401 and tentativa == 0 and renovar_token(sessao):
            continue
        return resposta
    return resposta


def _megabytes(n_bytes: int) -> str:
    return f"{n_bytes / (1024 * 1024):.1f} MB"


def inventariar_orfas(sessao: Sessao, saida: Path, carimbo: str,
                      imprimir: Callable[[str], None]) -> dict:
    """So leitura. Mostra o resumo e grava a lista completa de chaves."""
    resposta = _chamar(sessao, "GET", "/markets/EU/media/orphans")
    if resposta.status_code == 403:
        raise ErroFatal("Essa conta nao tem permissao de plataforma (platform_admin).")
    if resposta.status_code != 200:
        raise ErroFatal(f"Falha no inventario de orfas: {_detalhe(resposta)}")
    inv = resposta.json()
    orfas, bucket, varredura = inv["orphans"], inv["bucket"], inv["scan"]
    lista = saida / f"orfas-lista-{carimbo}.csv"
    with _abrir_csv(lista) as arq:
        escritor = csv.writer(arq, delimiter=";")
        escritor.writerow(["chave"])
        for chave in orfas["keys"]:
            escritor.writerow([chave])
    imprimir("")
    imprimir("Inventario de fotos orfas do bucket EU (nada foi alterado)")
    imprimir(f"  Varredura do banco: {'completa' if varredura['complete'] else 'INCOMPLETA'} "
             f"({varredura['columns_scanned']} colunas, {varredura['referenced_photo_ids']} fotos em uso)")
    imprimir(f"  Objetos no bucket (fotos): {bucket['total']['objects']}")
    imprimir(f"  Em uso (ficam): {bucket['referenced']['objects']}")
    imprimir(f"  Recentes, menos de {inv['grace_hours']} h (ficam): {bucket['kept_recent_24h']['objects']}")
    imprimir(f"  Nome fora do padrao (ficam): {bucket['kept_unrecognized_name']['objects']}")
    imprimir(f"  ORFAS: {orfas['objects']} objetos, {_megabytes(orfas['bytes'])}")
    for prefixo, dados in orfas["by_prefix"].items():
        if dados["objects"]:
            imprimir(f"      {prefixo}: {dados['objects']} ({_megabytes(dados['bytes'])})")
    for chave in orfas["sample"][:5]:
        imprimir(f"      ex.: {chave}")
    imprimir(f"  Lista completa das chaves: {lista}")
    if not inv["can_quarantine"]:
        imprimir(f"  BLOQUEADO por seguranca: {inv['blocked_reason']}")
    return inv


def _registrar_orfas(escritor, arq, acao: str, chave: str, status: str, mensagem: str = "",
                     agora: Callable[[], datetime] = datetime.now) -> None:
    escritor.writerow([agora().isoformat(timespec="seconds"), acao, chave, status, mensagem])
    arq.flush()


def mover_orfas_para_quarentena(
    sessao: Sessao, inventario: dict, log: Path, imprimir: Callable[[str], None],
    agora: Callable[[], datetime] = datetime.now,
) -> dict:
    """Move para eu-trash/ exatamente o conjunto inventariado, em lotes encadeados.
    Para no primeiro 409 (conjunto mudou) ou quando um lote nao avanca."""
    total = inventario["orphans"]["objects"]
    confirm = inventario["confirm"]
    movidas = falhas = 0
    with _abrir_csv(log) as arq:
        escritor = csv.writer(arq, delimiter=";")
        escritor.writerow(COLUNAS_LOG_ORFAS)
        while movidas + falhas < total:
            resposta = _chamar(
                sessao, "POST", "/markets/EU/media/orphans/purge",
                json_corpo={"confirm": confirm, "limit": LOTE_ORFAS},
            )
            if resposta.status_code != 200:
                msg = _detalhe(resposta)
                _registrar_orfas(escritor, arq, "quarentena", "", f"PAROU_{resposta.status_code}", msg, agora)
                imprimir(f"PAROU ({resposta.status_code}): {msg}")
                break
            dados = resposta.json()
            for chave in dados["moved"]:
                _registrar_orfas(escritor, arq, "quarentena", chave, "OK",
                                 f"eu-trash/{dados['quarantine_date']}/{chave}", agora)
            for item in dados["failed"]:
                _registrar_orfas(escritor, arq, "quarentena", item["key"], "ERRO", item["error"], agora)
            movidas += len(dados["moved"])
            falhas += len(dados["failed"])
            imprimir(f"  lote: {len(dados['moved'])} movidas, {len(dados['failed'])} falhas, "
                     f"restam {dados['remaining']}")
            confirm = dados["next_confirm"]
            if dados["remaining"] == 0 or not dados["moved"]:
                break
    return {"movidas": movidas, "falhas": falhas, "total": total}


def listar_quarentena(sessao: Sessao, imprimir: Callable[[str], None]) -> dict:
    resposta = _chamar(sessao, "GET", "/markets/EU/media/orphans/quarantine")
    if resposta.status_code != 200:
        raise ErroFatal(f"Falha ao consultar a quarentena: {_detalhe(resposta)}")
    dados = resposta.json()
    imprimir("")
    if not dados["batches"]:
        imprimir("Quarentena vazia.")
    for lote in dados["batches"]:
        situacao = ("pode apagar de vez" if lote["can_delete"]
                    else f"so apaga de vez com {dados['min_age_days']}+ dias")
        imprimir(f"  {lote['date']}: {lote['objects']} objetos, {_megabytes(lote['bytes'])}, "
                 f"{lote['age_days']} dia(s) - {situacao}")
    return dados


def restaurar_quarentena(sessao: Sessao, data: str, log: Path,
                         imprimir: Callable[[str], None],
                         agora: Callable[[], datetime] = datetime.now) -> int:
    total = 0
    with _abrir_csv(log) as arq:
        escritor = csv.writer(arq, delimiter=";")
        escritor.writerow(COLUNAS_LOG_ORFAS)
        while True:
            resposta = _chamar(sessao, "POST", "/markets/EU/media/orphans/quarantine/restore",
                               json_corpo={"date": data, "limit": LOTE_ORFAS})
            if resposta.status_code != 200:
                raise ErroFatal(f"Falha ao restaurar: {_detalhe(resposta)}")
            dados = resposta.json()
            for chave in dados["restored"]:
                _registrar_orfas(escritor, arq, "restaurar", chave, "OK", "", agora)
            for item in dados["failed"]:
                _registrar_orfas(escritor, arq, "restaurar", item["key"], "ERRO", item["error"], agora)
            total += len(dados["restored"])
            imprimir(f"  lote: {len(dados['restored'])} restauradas, restam {dados['remaining']}")
            if dados["remaining"] == 0 or not dados["restored"]:
                return total


def apagar_quarentena(sessao: Sessao, lote: dict, log: Path, imprimir: Callable[[str], None],
                      agora: Callable[[], datetime] = datetime.now) -> int:
    confirm, total = lote["confirm"], 0
    with _abrir_csv(log) as arq:
        escritor = csv.writer(arq, delimiter=";")
        escritor.writerow(COLUNAS_LOG_ORFAS)
        while True:
            resposta = _chamar(sessao, "POST", "/markets/EU/media/orphans/quarantine/delete",
                               json_corpo={"date": lote["date"], "confirm": confirm, "limit": LOTE_ORFAS})
            if resposta.status_code != 200:
                raise ErroFatal(f"Falha ao apagar a quarentena: {_detalhe(resposta)}")
            dados = resposta.json()
            for chave in dados["deleted"]:
                _registrar_orfas(escritor, arq, "apagar_de_vez", chave, "OK", "", agora)
            for item in dados["failed"]:
                _registrar_orfas(escritor, arq, "apagar_de_vez", item["key"], "ERRO", item["error"], agora)
            total += len(dados["deleted"])
            imprimir(f"  lote: {len(dados['deleted'])} apagadas, restam {dados['remaining']}")
            confirm = dados["next_confirm"]
            if dados["remaining"] == 0 or not dados["deleted"]:
                return total


def executar_orfas(
    args: argparse.Namespace, sessao: Sessao, carimbo: str,
    entrada: Callable[[str], str], imprimir: Callable[[str], None],
) -> int:
    """Passos de fotos orfas. Cada acao que altera algo pede confirmacao digitada."""
    if args.restaurar:
        lista = listar_quarentena(sessao, imprimir)
        if args.restaurar not in {b["date"] for b in lista["batches"]}:
            raise ErroFatal(f"Nao ha lote de quarentena em {args.restaurar}.")
        log = args.saida / f"log-orfas-restaurar-{carimbo}.csv"
        n = restaurar_quarentena(sessao, args.restaurar, log, imprimir)
        imprimir(f"\n{n} fotos voltaram ao lugar de origem. Log: {log}")
        return 0

    if args.esvaziar_quarentena:
        lista = listar_quarentena(sessao, imprimir)
        lote = next((b for b in lista["batches"] if b["date"] == args.esvaziar_quarentena), None)
        if lote is None:
            raise ErroFatal(f"Nao ha lote de quarentena em {args.esvaziar_quarentena}.")
        if not lote["can_delete"]:
            raise ErroFatal(f"Esse lote tem {lote['age_days']} dia(s); so pode ser apagado de vez "
                            f"com {lista['min_age_days']}+ dias.")
        if not args.sim:
            resposta = entrada(
                f"\nIRREVERSIVEL: apagar de vez {lote['objects']} fotos ({_megabytes(lote['bytes'])}) "
                f"da quarentena de {lote['date']}. Digite {CONFIRMACAO_DEFINITIVA} para continuar: ")
            if resposta.strip() != CONFIRMACAO_DEFINITIVA:
                imprimir("Cancelado. Nada foi alterado.")
                return 1
        log = args.saida / f"log-orfas-apagar-definitivo-{carimbo}.csv"
        n = apagar_quarentena(sessao, lote, log, imprimir)
        imprimir(f"\n{n} fotos apagadas de vez. Log: {log}")
        return 0

    if args.quarentena:
        listar_quarentena(sessao, imprimir)
        return 0

    inventario = inventariar_orfas(sessao, args.saida, carimbo, imprimir)
    if not args.apagar:
        imprimir("\nNada foi alterado. Confira o numero e, se estiver certo, rode de novo "
                 "com --orfas --apagar.")
        return 0
    if not inventario["can_quarantine"]:
        return 1
    if inventario["orphans"]["objects"] == 0:
        imprimir("\nNao ha fotos orfas.")
        return 0
    if not args.sim:
        resposta = entrada(
            f"\nVai MOVER {inventario['orphans']['objects']} fotos orfas "
            f"({_megabytes(inventario['orphans']['bytes'])}) para a quarentena eu-trash/ do "
            f"bucket EU. Nada some de vez agora; da para restaurar. "
            f"Digite {CONFIRMACAO_ORFAS} para continuar: ")
        if resposta.strip() != CONFIRMACAO_ORFAS:
            imprimir("Cancelado. Nada foi alterado.")
            return 1
    log = args.saida / f"log-orfas-quarentena-{carimbo}.csv"
    resultado = mover_orfas_para_quarentena(sessao, inventario, log, imprimir)
    imprimir("")
    imprimir(f"Resultado: {resultado['movidas']} movidas para a quarentena, "
             f"{resultado['falhas']} falhas, de {resultado['total']} previstas.")
    imprimir(f"Log: {log}")
    imprimir("Para desfazer: --orfas --restaurar AAAA-MM-DD. Para apagar de vez (so apos 7 dias): "
             "--orfas --esvaziar-quarentena AAAA-MM-DD.")
    return 0 if resultado["falhas"] == 0 and resultado["movidas"] == resultado["total"] else 2


# --------------------------------------------------------------------------- #
# Linha de comando
# --------------------------------------------------------------------------- #

def _argumentos(argv: list[str] | None) -> argparse.Namespace:
    raiz = Path(__file__).resolve().parent.parent
    p = argparse.ArgumentParser(
        description="Troca fotos do mercado EU por arquivos <CODIGO>.jpeg de uma pasta "
                    "e limpa fotos orfas do bucket EU."
    )
    p.add_argument("pasta", type=Path, nargs="?",
                   help="Pasta com os arquivos <CODIGO>.jpeg (nao usada com --orfas)")
    p.add_argument("--orfas", action="store_true",
                   help="Fotos orfas do bucket EU: so lista (inventario), nao altera nada.")
    p.add_argument("--apagar", action="store_true",
                   help="Com --orfas: move as orfas para a quarentena (pede para digitar APAGAR).")
    p.add_argument("--quarentena", action="store_true",
                   help="Com --orfas: lista os lotes que estao na quarentena.")
    p.add_argument("--restaurar", metavar="AAAA-MM-DD", default="",
                   help="Com --orfas: devolve um lote da quarentena ao lugar de origem.")
    p.add_argument("--esvaziar-quarentena", metavar="AAAA-MM-DD", default="",
                   help="Com --orfas: apaga DE VEZ um lote com 7+ dias (irreversivel).")
    p.add_argument("--apply", action="store_true",
                   help="Troca as fotos de verdade. Sem isso e so simulacao (dry-run).")
    p.add_argument("--base-url", default=os.environ.get("ILYA_API_URL", ""),
                   help=f"Base da API (padrao: {BASE_URL_PADRAO}; com --orfas: "
                        f"{BASE_URL_PLATAFORMA}, que nao passa pelo proxy da Vercel).")
    p.add_argument("--origin", default=ORIGEM_PADRAO,
                   help="Origem enviada nas rotas de cookie (precisa estar na lista do CORS).")
    p.add_argument("--saida", type=Path, default=raiz / "logs" / "fotos-eu",
                   help="Pasta dos relatorios (padrao: logs/fotos-eu, fora do git).")
    p.add_argument("--pausa", type=float, default=1.0, help="Segundos entre trocas (padrao 1).")
    p.add_argument("--somente", default="",
                   help="So estes codigos, separados por virgula (bom para testar com 1 produto).")
    p.add_argument("--sim", action="store_true",
                   help="Com --apply, nao pergunta a confirmacao digitada.")
    return p.parse_args(argv)


def main(
    argv: list[str] | None = None,
    *,
    client: httpx.Client | None = None,
    entrada: Callable[[str], str] = input,
    senha: Callable[[str], str] = getpass.getpass,
    dormir: Callable[[float], None] = time.sleep,
    imprimir: Callable[[str], None] = print,
    ambiente: dict | None = None,
) -> int:
    args = _argumentos(argv)
    ambiente = os.environ if ambiente is None else ambiente
    carimbo = datetime.now().strftime("%Y%m%d-%H%M%S")
    modo = "APLICAR (altera o site)" if args.apply else "DRY-RUN (nao altera nada)"

    sub_orfas = (args.apagar, args.quarentena, args.restaurar, args.esvaziar_quarentena)
    if args.orfas:
        if args.pasta or args.apply or args.somente:
            imprimir("ERRO: --orfas nao usa pasta, --apply nem --somente. "
                     "As fotos orfas e a troca de fotos sao passos separados.")
            return 1
        if sum(1 for opcao in sub_orfas if opcao) > 1:
            imprimir("ERRO: use so uma acao por vez com --orfas.")
            return 1
    else:
        if any(sub_orfas):
            imprimir("ERRO: --apagar, --quarentena, --restaurar e --esvaziar-quarentena "
                     "so valem junto com --orfas.")
            return 1
        if args.pasta is None:
            imprimir("ERRO: informe a pasta das fotos (ou use --orfas).")
            return 1

    proprio_client = client is None
    if client is None:
        client = httpx.Client(timeout=30.0, follow_redirects=False)
    client.headers.update({"Origin": args.origin})
    base_url = args.base_url or (BASE_URL_PLATAFORMA if args.orfas else BASE_URL_PADRAO)
    sessao = Sessao(client=client, base_url=base_url, plataforma=args.orfas)

    try:
        if args.orfas:
            imprimir("Modo: FOTOS ORFAS DO BUCKET EU")
            autenticar(
                sessao,
                token_env=ambiente.get("ILYA_TOKEN"),
                pedir_usuario=lambda: entrada("Usuario ou e-mail (conta de plataforma): "),
                pedir_senha=lambda: senha("Senha (nao aparece ao digitar): "),
            )
            return executar_orfas(args, sessao, carimbo, entrada, imprimir)

        arquivos, ignorados = listar_arquivos(args.pasta)
        if args.somente:
            pedidos = {normalizar_codigo(c) for c in args.somente.split(",") if c.strip()}
            arquivos = {c: v for c, v in arquivos.items() if c in pedidos}
        if not arquivos:
            raise ErroFatal("Nenhum arquivo de foto encontrado para processar.")

        imprimir(f"Modo: {modo}")
        imprimir(f"Fotos lidas na pasta: {len(arquivos)}")
        autenticar(
            sessao,
            token_env=ambiente.get("ILYA_TOKEN"),
            pedir_usuario=lambda: entrada("Usuario ou e-mail: "),
            pedir_senha=lambda: senha("Senha (nao aparece ao digitar): "),
        )
        produtos = buscar_produtos_eu(sessao)
        imprimir(f"Produtos EU ativos no site: {len(produtos)}")

        plano = montar_plano(arquivos, produtos)
        envolvidos = {l.codigo for l in plano if l.status == VAI_TROCAR}
        relatorio = args.saida / f"relatorio-{'apply' if args.apply else 'dry-run'}-{carimbo}.csv"
        backup = args.saida / f"backup-fotos-antigas-{carimbo}.csv"
        salvar_relatorio(relatorio, plano)
        n_backup = salvar_backup(backup, produtos, envolvidos)
        contagem = resumir(plano, ignorados)
        imprimir("")
        imprimir(texto_resumo(contagem, args.pasta, modo))
        imprimir("")
        imprimir(f"Relatorio: {relatorio}")
        imprimir(f"Backup (so referencia, {n_backup} produtos): {backup}")
        imprimir("ATENCAO: o backup lista as fotos antigas, mas NAO guarda os arquivos. "
                 "As fotos antigas do bucket EU sao apagadas na troca e nao voltam, "
                 "EXCETO as que outro produto, opcional ou pedido ainda usa: essas ficam.")

        if not args.apply:
            imprimir("\nNada foi alterado. Para trocar de verdade rode de novo com --apply.")
            return 0
        if not envolvidos:
            imprimir("\nNao ha nada para trocar.")
            return 0
        if not args.sim:
            resposta = entrada(
                f"\nVai trocar {len(envolvidos)} fotos no mercado EU e apagar as antigas. "
                f"Digite {CONFIRMACAO} para continuar: "
            )
            if resposta.strip() != CONFIRMACAO:
                imprimir("Cancelado. Nada foi alterado.")
                return 1

        log = args.saida / f"log-apply-{carimbo}.csv"
        resultado = aplicar(sessao, plano, log, pausa=args.pausa, dormir=dormir, imprimir=imprimir)
        imprimir("")
        imprimir(
            f"Resultado: {resultado[OK]} trocadas, {resultado[COMPARTILHADO_BR]} compartilhadas "
            f"com o BR (puladas), {resultado[ERRO]} com erro, {resultado[NAO_TENTADO]} nao tentadas."
        )
        imprimir(f"Log: {log}")
        return 0 if resultado[ERRO] == 0 and resultado[NAO_TENTADO] == 0 else 2
    except ErroFatal as erro:
        imprimir(f"\nERRO: {erro}")
        return 1
    except httpx.HTTPError as erro:
        imprimir(f"\nERRO de rede: {type(erro).__name__}. Nada foi trocado depois deste ponto.")
        return 1
    finally:
        if proprio_client:
            client.close()


if __name__ == "__main__":
    sys.exit(main())
