"""Testes de `ops/trocar_fotos_eu.py` com a API simulada (httpx.MockTransport).

Nenhum teste fala com a rede nem com producao. Rodar na raiz do repo:
    py -m unittest ops/test_trocar_fotos_eu.py
"""

from __future__ import annotations

import base64
import csv
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ops import trocar_fotos_eu as t  # noqa: E402

SENHA_FALSA = "senha-de-teste-123"


def _jwt(market: str, versao: int = 0) -> str:
    def b64(obj: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip("=")

    return f"{b64({'alg': 'none'})}.{b64({'market': market, 'role': 'admin', 'n': versao})}.x"


def _url_foto(chave: str) -> str:
    return f"/api/v1/media/{chave}?expires=1&signature=abc"


class ApiFalsa:
    """Imita so o que o script usa: login, switch-market, refresh, listagem e upload."""

    def __init__(self, produtos, *, home="BR", compartilhados=(), falhas=None,
                 vencer_token_na_chamada=None, pagina=2):
        self.produtos = produtos  # list[dict(id, product_code, photo)]
        self.home = home
        self.compartilhados = set(compartilhados)
        self.falhas = falhas or {}  # product_code -> status HTTP forcado
        self.vencer_na = vencer_token_na_chamada  # n-esimo upload devolve 401 uma vez
        self.pagina = pagina
        self.uploads = 0
        self.tokens_validos = set()
        self.chamadas: list[tuple[str, str]] = []
        self.origens: set[str | None] = set()
        self.apagadas: list[str] = []
        self.refresh_ok = True
        self._n = 0

    def _novo_token(self, market):
        self._n += 1
        token = _jwt(market, self._n)
        self.tokens_validos.add(token)
        return token

    def handler(self, req: httpx.Request) -> httpx.Response:
        caminho = req.url.path
        self.chamadas.append((req.method, caminho))
        self.origens.add(req.headers.get("origin"))
        if caminho.endswith("/auth/login"):
            corpo = json.loads(req.content)
            if corpo["password"] != SENHA_FALSA:
                return httpx.Response(401, json={"detail": "Usuário ou senha incorretos."})
            return httpx.Response(200, json={"access_token": self._novo_token(self.home)})
        if caminho.endswith("/auth/refresh"):
            if not self.refresh_ok:
                return httpx.Response(204)
            return httpx.Response(200, json={"access_token": self._novo_token("EU")})
        autorizado = req.headers.get("authorization", "").removeprefix("Bearer ")
        if caminho.endswith("/auth/switch-market"):
            return httpx.Response(200, json={"access_token": self._novo_token("EU")})
        if autorizado not in self.tokens_validos:
            return httpx.Response(401, json={"detail": "Credenciais inválidas ou token expirado."})
        if req.method == "GET" and caminho.endswith("/products"):
            params = req.url.params
            pulo, limite = int(params["skip"]), min(int(params["limit"]), self.pagina)
            fatia = self.produtos[pulo:pulo + limite]
            mais = pulo + len(fatia) < len(self.produtos)
            return httpx.Response(
                200,
                json=[{"id": p["id"], "product_code": p["product_code"],
                       "photo_url": _url_foto(p["photo"]) if p["photo"] else None} for p in fatia],
                headers={"X-Has-More": "true" if mais else "false"},
            )
        if req.method == "POST" and caminho.endswith("/upload-photo"):
            self.uploads += 1
            if self.vencer_na == self.uploads:
                self.vencer_na = None
                self.tokens_validos.discard(autorizado)
                return httpx.Response(401, json={"detail": "expirado"})
            produto_id = caminho.split("/")[-2]
            produto = next(p for p in self.produtos if p["id"] == produto_id)
            if produto["product_code"] in self.falhas:
                return httpx.Response(self.falhas[produto["product_code"]], json={"detail": "falha simulada"})
            if produto["product_code"] in self.compartilhados:
                return httpx.Response(403, json={"detail": "Altere as fotos do catálogo-base no mercado Brasil."})
            assert b"filename=" in req.content and b"image/jpeg" in req.content
            if produto["photo"] and produto["photo"].startswith("eu-"):
                self.apagadas.append(produto["photo"])
            produto["photo"] = f"eu-products/novo-{self.uploads}.webp"
            return httpx.Response(200, json={"id": produto_id, "product_code": produto["product_code"],
                                             "photo_url": _url_foto(produto["photo"])})
        return httpx.Response(404, json={"detail": "rota inesperada"})


def _produtos():
    return [
        {"id": "id-1", "product_code": "AC0105", "photo": "eu-products/velha1.webp"},
        {"id": "id-2", "product_code": "SF0597", "photo": "products/do-brasil.webp"},
        {"id": "id-3", "product_code": "BC0023", "photo": None},
        {"id": "id-4", "product_code": "DUP001", "photo": "eu-products/d1.webp"},
        {"id": "id-5", "product_code": "DUP001", "photo": "eu-products/d2.webp"},
        {"id": "id-6", "product_code": "SH0001", "photo": "eu-products/shared.webp"},
        {"id": "id-7", "product_code": "ER0001", "photo": "eu-products/err.webp"},
    ]


class TesteBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.raiz = Path(self.tmp.name)
        self.pasta = self.raiz / "IBTW"
        self.pasta.mkdir()
        self.saida = self.raiz / "saida"
        for nome in ["AC0105.jpeg", "SF0597.jpeg", "BC0023.jpeg", "DUP001.jpeg", "SH0001.jpeg",
                     "ER0001.jpeg", "NAOEXISTE.jpeg", "Thumbs.db", "LEIAME.txt"]:
            (self.pasta / nome).write_bytes(b"\xff\xd8\xff fake jpeg")
        self.saidas: list[str] = []

    def rodar(self, api: ApiFalsa, *extra, ambiente=None, entradas=None, senha=SENHA_FALSA):
        entradas = list(entradas or ["fulano@ilya.com"])
        client = httpx.Client(transport=httpx.MockTransport(api.handler))
        return t.main(
            [str(self.pasta), "--saida", str(self.saida), "--pausa", "0", *extra],
            client=client,
            entrada=lambda _p: entradas.pop(0),
            senha=lambda _p: senha,
            dormir=lambda _s: None,
            imprimir=self.saidas.append,
            ambiente=ambiente if ambiente is not None else {},
        )

    def csvs(self, prefixo):
        achados = sorted(self.saida.glob(f"{prefixo}-*.csv")) if self.saida.exists() else []
        if not achados:
            return None
        with open(achados[-1], newline="", encoding="utf-8-sig") as arq:
            return list(csv.DictReader(arq, delimiter=";"))


class TesteDryRun(TesteBase):
    def test_dry_run_classifica_e_nao_altera_nada(self):
        api = ApiFalsa(_produtos())
        self.assertEqual(self.rodar(api), 0)

        self.assertFalse([c for c in api.chamadas if c[0] == "POST" and "upload" in c[1]])
        self.assertEqual(api.uploads, 0)
        relatorio = {l["codigo"]: l for l in self.csvs("relatorio-dry-run")}
        self.assertEqual(relatorio["AC0105"]["status"], t.VAI_TROCAR)
        self.assertEqual(relatorio["AC0105"]["foto_atual_chave"], "eu-products/velha1.webp")
        self.assertIn("bucket EU", relatorio["AC0105"]["foto_atual_origem"])
        self.assertIn("BR", relatorio["SF0597"]["foto_atual_origem"])
        self.assertEqual(relatorio["BC0023"]["foto_atual_origem"], "sem foto")
        self.assertEqual(relatorio["DUP001"]["status"], t.CODIGO_DUPLICADO)
        self.assertEqual(relatorio["NAOEXISTE"]["status"], t.SEM_PRODUTO)
        self.assertNotIn("THUMBS", relatorio)
        self.assertEqual(len(relatorio), 7)

    def test_backup_so_dos_que_vao_trocar(self):
        self.rodar(ApiFalsa(_produtos()))
        backup = {l["product_code"]: l for l in self.csvs("backup-fotos-antigas")}
        self.assertEqual(set(backup), {"AC0105", "SF0597", "BC0023", "SH0001", "ER0001"})
        self.assertEqual(backup["AC0105"]["foto_antiga_chave"], "eu-products/velha1.webp")
        self.assertIn("NAO guarda os arquivos", "\n".join(self.saidas))

    def test_troca_mercado_br_para_eu_e_envia_origin(self):
        api = ApiFalsa(_produtos(), home="BR")
        self.rodar(api)
        self.assertIn(("POST", "/api/v1/auth/switch-market"), api.chamadas)
        self.assertEqual(api.origens, {t.ORIGEM_PADRAO})

    def test_paginacao_le_todos_os_produtos(self):
        api = ApiFalsa(_produtos(), pagina=2)
        self.rodar(api)
        gets = [c for c in api.chamadas if c == ("GET", "/api/v1/products")]
        self.assertEqual(len(gets), 4)  # 7 produtos, 2 por pagina

    def test_senha_errada_para_sem_listar_nada(self):
        api = ApiFalsa(_produtos())
        self.assertEqual(self.rodar(api, senha="errada"), 1)
        self.assertNotIn(("GET", "/api/v1/products"), api.chamadas)
        self.assertIn("Login recusado", "\n".join(self.saidas))

    def test_senha_e_token_nunca_aparecem_na_saida_nem_nos_arquivos(self):
        api = ApiFalsa(_produtos())
        self.rodar(api, "--apply", "--sim")
        texto = "\n".join(self.saidas)
        for arquivo in self.saida.glob("*.csv"):
            texto += arquivo.read_text(encoding="utf-8-sig")
        self.assertNotIn(SENHA_FALSA, texto)
        for token in api.tokens_validos:
            self.assertNotIn(token, texto)

    def test_token_de_ambiente_nao_pede_senha_e_exige_mercado_eu(self):
        api = ApiFalsa(_produtos())
        eu = api._novo_token("EU")
        client = httpx.Client(transport=httpx.MockTransport(api.handler))
        t.main([str(self.pasta), "--saida", str(self.saida)], client=client,
               entrada=lambda _p: self.fail("nao deveria pedir usuario"),
               senha=lambda _p: self.fail("nao deveria pedir senha"),
               imprimir=self.saidas.append, ambiente={"ILYA_TOKEN": eu})
        self.assertNotIn(("POST", "/api/v1/auth/login"), api.chamadas)

        self.saidas.clear()
        codigo = t.main([str(self.pasta), "--saida", str(self.saida)], client=client,
                        imprimir=self.saidas.append, ambiente={"ILYA_TOKEN": _jwt("BR")})
        self.assertEqual(codigo, 1)
        self.assertIn("nao e do mercado EU", "\n".join(self.saidas))

    def test_somente_filtra_codigos(self):
        self.rodar(ApiFalsa(_produtos()), "--somente", "ac0105")
        relatorio = self.csvs("relatorio-dry-run")
        self.assertEqual([l["codigo"] for l in relatorio], ["AC0105"])

    def test_pasta_inexistente(self):
        codigo = t.main([str(self.raiz / "nada"), "--saida", str(self.saida)],
                        imprimir=self.saidas.append, ambiente={})
        self.assertEqual(codigo, 1)


class TesteApply(TesteBase):
    def test_apply_troca_pula_compartilhado_e_continua_apos_erro(self):
        api = ApiFalsa(_produtos(), compartilhados={"SH0001"}, falhas={"ER0001": 500})
        codigo = self.rodar(api, "--apply", "--sim")
        self.assertEqual(codigo, 2)  # houve erro, mas o resto foi feito

        log = {l["codigo"]: l for l in self.csvs("log-apply")}
        self.assertEqual(log["AC0105"]["status"], t.OK)
        self.assertTrue(log["AC0105"]["foto_nova_chave"].startswith("eu-products/novo-"))
        self.assertEqual(log["AC0105"]["foto_antiga_apagada_pelo_servidor"], "sim")
        self.assertEqual(log["SF0597"]["status"], t.OK)  # foto herdada do BR
        self.assertTrue(log["SF0597"]["foto_antiga_apagada_pelo_servidor"].startswith("nao"))
        self.assertEqual(log["BC0023"]["status"], t.OK)  # sem foto antes
        self.assertEqual(log["SH0001"]["status"], t.COMPARTILHADO_BR)
        self.assertEqual(log["ER0001"]["status"], t.ERRO)
        self.assertEqual(log["ER0001"]["http"], "500")
        self.assertNotIn("DUP001", log)
        self.assertNotIn("NAOEXISTE", log)
        self.assertEqual(api.uploads, 5)
        self.assertIn("3 trocadas, 1 compartilhadas", "\n".join(self.saidas))

    def test_apply_pede_confirmacao_e_cancela(self):
        api = ApiFalsa(_produtos())
        codigo = self.rodar(api, "--apply", entradas=["fulano@ilya.com", "nao"])
        self.assertEqual(codigo, 1)
        self.assertEqual(api.uploads, 0)

    def test_apply_com_confirmacao_correta(self):
        api = ApiFalsa(_produtos())
        codigo = self.rodar(api, "--apply", "--somente", "AC0105",
                            entradas=["fulano@ilya.com", "TROCAR"])
        self.assertEqual(codigo, 0)
        self.assertEqual(api.uploads, 1)
        self.assertEqual(api.apagadas, ["eu-products/velha1.webp"])

    def test_token_vence_no_meio_renova_e_segue(self):
        api = ApiFalsa(_produtos(), vencer_token_na_chamada=2)
        codigo = self.rodar(api, "--apply", "--sim", "--somente", "AC0105,SF0597,BC0023")
        self.assertEqual(codigo, 0)
        self.assertEqual([l["status"] for l in self.csvs("log-apply")], [t.OK, t.OK, t.OK])
        self.assertIn(("POST", "/api/v1/auth/refresh"), api.chamadas)

    def test_token_vence_sem_como_renovar_para_com_aviso(self):
        api = ApiFalsa(_produtos(), vencer_token_na_chamada=2)
        api.refresh_ok = False
        codigo = self.rodar(api, "--apply", "--sim", "--somente", "AC0105,SF0597,BC0023")
        self.assertEqual(codigo, 2)
        status = [l["status"] for l in self.csvs("log-apply")]
        self.assertEqual(status, [t.OK, t.NAO_TENTADO, t.NAO_TENTADO])

    def test_rodar_de_novo_apenas_troca_de_novo(self):
        api = ApiFalsa(_produtos())
        self.rodar(api, "--apply", "--sim", "--somente", "AC0105")
        # segunda rodada enxerga a foto nova que a primeira gravou
        self.rodar(api, "--apply", "--sim", "--somente", "AC0105")
        self.assertEqual(api.uploads, 2)
        self.assertEqual(api.apagadas, ["eu-products/velha1.webp", "eu-products/novo-1.webp"])


class TesteFuncoes(unittest.TestCase):
    def test_extrair_chave(self):
        self.assertEqual(
            t.extrair_chave("/api/v1/media/eu-products/a%20b.webp?expires=1&signature=z"),
            "eu-products/a b.webp",
        )
        self.assertEqual(t.extrair_chave(None), "")
        self.assertEqual(t.extrair_chave("https://x.com/outra/coisa.png"), "")

    def test_listar_arquivos_ignora_thumbs_e_detecta_duplicado(self):
        with tempfile.TemporaryDirectory() as d:
            pasta = Path(d)
            for nome in ["ab0001.jpeg", "AB0001.jpg", "Thumbs.db", "CD0002.JPEG"]:
                (pasta / nome).write_bytes(b"x")
            arquivos, ignorados = t.listar_arquivos(pasta)
            self.assertEqual(len(arquivos["AB0001"]), 2)
            self.assertIn("CD0002", arquivos)
            self.assertEqual(ignorados, ["Thumbs.db"])


if __name__ == "__main__":
    unittest.main()
