"""Testes dos passos de fotos órfãs de `ops/trocar_fotos_eu.py` (API simulada).

A API falsa imita as rotas `/markets/EU/media/orphans...`: `confirm` precisa ser o
token exato do conjunto atual (`<quantidade>-<hash>`), o lote devolve o token do
que sobrou, e a quarentena só apaga de vez com 7+ dias. Nada toca a rede.

    py -m unittest ops/test_trocar_fotos_eu_orfas.py
"""

from __future__ import annotations

import base64
import csv
import hashlib
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


def _jwt(payload: dict) -> str:
    def b64(obj: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip("=")

    return f"{b64({'alg': 'none'})}.{b64(payload)}.x"


def _token_do_conjunto(chaves) -> str:
    """Mesma regra do servidor: `<quantidade>-<sha256 das chaves ordenadas>[:16]`."""
    ordenadas = sorted(chaves)
    digest = hashlib.sha256("\n".join(ordenadas).encode()).hexdigest()[:16]
    return f"{len(ordenadas)}-{digest}"


class ApiOrfasFalsa:
    def __init__(self, orfas, *, quarentena=None, bloqueado=None, permissao=True, idade_dias=10):
        self.orfas = sorted(orfas)
        self.quarentena = dict(quarentena or {})  # data -> [chaves originais]
        self.bloqueado = bloqueado
        self.permissao = permissao
        self.idade_dias = idade_dias
        self.tokens: set[str] = set()
        self.chamadas: list[tuple[str, str]] = []
        self.corpos: list[dict] = []
        self.emitidos = 0

    def novo_token(self) -> str:
        self.emitidos += 1
        token = _jwt({"scope": "platform", "n": self.emitidos})
        self.tokens.add(token)
        return token

    def handler(self, req: httpx.Request) -> httpx.Response:
        caminho = req.url.path
        self.chamadas.append((req.method, caminho))
        if caminho.endswith("/platform/auth/login"):
            if json.loads(req.content)["password"] != SENHA_FALSA:
                return httpx.Response(401, json={"detail": "Usuário ou senha incorretos."})
            if not self.permissao:
                return httpx.Response(403, json={"detail": "Acesso de plataforma não concedido."})
            return httpx.Response(200, json={"access_token": self.novo_token()})
        if caminho.endswith("/platform/auth/refresh"):
            return httpx.Response(200, json={"access_token": self.novo_token()})
        if req.headers.get("authorization", "").removeprefix("Bearer ") not in self.tokens:
            return httpx.Response(401, json={"detail": "expirado"})
        corpo = json.loads(req.content) if req.content else {}
        self.corpos.append(corpo)
        if caminho.endswith("/orphans") and req.method == "GET":
            return httpx.Response(200, json={
                "scan": {"complete": self.bloqueado is None, "columns_scanned": 80,
                         "unreadable_columns": [], "referenced_photo_ids": 300},
                "bucket": {"total": {"objects": 900}, "referenced": {"objects": 880, "bytes": 1},
                           "kept_recent_24h": {"objects": 2, "bytes": 1},
                           "kept_unrecognized_name": {"objects": 0, "bytes": 0}},
                "orphans": {"objects": len(self.orfas), "bytes": 5 * 1024 * 1024,
                            "by_prefix": {"eu-products": {"objects": len(self.orfas), "bytes": 1}},
                            "sample": self.orfas[:20], "keys": list(self.orfas)},
                "can_quarantine": self.bloqueado is None, "blocked_reason": self.bloqueado,
                "confirm": _token_do_conjunto(self.orfas), "grace_hours": 24,
            })
        if caminho.endswith("/orphans/purge"):
            if corpo["confirm"] != _token_do_conjunto(self.orfas):
                return httpx.Response(409, json={"detail": "O conjunto de órfãs mudou."})
            lote = self.orfas[:corpo["limit"]]
            self.orfas = self.orfas[len(lote):]
            self.quarentena.setdefault("2026-11-10", []).extend(lote)
            return httpx.Response(200, json={
                "quarantine_date": "2026-11-10", "moved": lote, "failed": [],
                "remaining": len(self.orfas), "next_confirm": _token_do_conjunto(self.orfas)})
        if caminho.endswith("/orphans/quarantine") and req.method == "GET":
            return httpx.Response(200, json={"min_age_days": 7, "batches": [
                {"date": d, "objects": len(k), "bytes": 10, "age_days": self.idade_dias,
                 "can_delete": self.idade_dias >= 7, "confirm": _token_do_conjunto(k)}
                for d, k in sorted(self.quarentena.items()) if k]})
        if caminho.endswith("/quarantine/restore"):
            lote = self.quarentena.get(corpo["date"], [])[:corpo["limit"]]
            self.quarentena[corpo["date"]] = self.quarentena[corpo["date"]][len(lote):]
            self.orfas = sorted(self.orfas + lote)
            return httpx.Response(200, json={"date": corpo["date"], "restored": lote, "failed": [],
                                             "remaining": len(self.quarentena[corpo["date"]])})
        if caminho.endswith("/quarantine/delete"):
            atual = self.quarentena.get(corpo["date"], [])
            if corpo["confirm"] != _token_do_conjunto(atual):
                return httpx.Response(409, json={"detail": "O lote mudou."})
            lote = atual[:corpo["limit"]]
            self.quarentena[corpo["date"]] = atual[len(lote):]
            return httpx.Response(200, json={
                "date": corpo["date"], "deleted": lote, "failed": [],
                "remaining": len(self.quarentena[corpo["date"]]),
                "next_confirm": _token_do_conjunto(self.quarentena[corpo["date"]])})
        return httpx.Response(404, json={"detail": "rota inesperada"})


def _chaves(n: int) -> list[str]:
    return [f"eu-products/{i:08d}-0000-4000-8000-000000000000.webp" for i in range(n)]


class TesteOrfas(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.saida = Path(self.tmp.name) / "saida"
        self.saidas: list[str] = []

    def rodar(self, api, *args, entradas=None, senha=SENHA_FALSA, ambiente=None, handler=None):
        entradas = list(entradas if entradas is not None else ["admin@ilya.com"])
        client = httpx.Client(transport=httpx.MockTransport(handler or api.handler))
        return t.main(["--saida", str(self.saida), *args], client=client,
                      entrada=lambda _p: entradas.pop(0), senha=lambda _p: senha,
                      imprimir=self.saidas.append, ambiente=ambiente or {})

    def texto(self) -> str:
        return "\n".join(self.saidas)

    def csv_de(self, prefixo):
        achados = sorted(self.saida.glob(f"{prefixo}-*.csv"))
        if not achados:
            return None
        with open(achados[-1], newline="", encoding="utf-8-sig") as arq:
            return list(csv.DictReader(arq, delimiter=";"))

    def test_so_lista_usa_login_de_plataforma_e_nao_altera(self):
        api = ApiOrfasFalsa(_chaves(5))
        self.assertEqual(self.rodar(api, "--orfas"), 0)
        self.assertIn(("POST", "/api/v1/platform/auth/login"), api.chamadas)
        self.assertNotIn(("POST", "/api/v1/auth/login"), api.chamadas)
        self.assertFalse([c for c in api.chamadas if "purge" in c[1] or "delete" in c[1]])
        self.assertIn("ORFAS: 5 objetos, 5.0 MB", self.texto())
        self.assertEqual([l["chave"] for l in self.csv_de("orfas-lista")], _chaves(5))
        self.assertEqual(len(api.orfas), 5)

    def test_usa_a_api_de_plataforma_fora_do_proxy_da_vercel(self):
        api = ApiOrfasFalsa(_chaves(1))
        urls = []

        def espiao(req):
            urls.append(str(req.url))
            return api.handler(req)

        self.rodar(api, "--orfas", handler=espiao)
        self.assertTrue(urls and all(u.startswith(t.BASE_URL_PLATAFORMA) for u in urls))

    def test_apagar_pede_APAGAR_e_cancela_com_outra_resposta(self):
        api = ApiOrfasFalsa(_chaves(3))
        self.assertEqual(self.rodar(api, "--orfas", "--apagar", entradas=["admin", "sim"]), 1)
        self.assertEqual(len(api.orfas), 3)
        self.assertFalse([c for c in api.chamadas if "purge" in c[1]])

    def test_apagar_move_em_lotes_encadeados_e_registra_log(self):
        api = ApiOrfasFalsa(_chaves(450))
        codigo = self.rodar(api, "--orfas", "--apagar", entradas=["admin", "APAGAR"])
        self.assertEqual(codigo, 0)
        self.assertEqual(api.orfas, [])
        self.assertEqual(len(api.quarentena["2026-11-10"]), 450)
        limites = [c["limit"] for c in api.corpos if "limit" in c and "confirm" in c]
        self.assertEqual(limites, [200, 200, 200])
        log = self.csv_de("log-orfas-quarentena")
        self.assertEqual(len(log), 450)
        self.assertTrue(all(l["status"] == "OK" and l["acao"] == "quarentena" for l in log))
        self.assertIn("--restaurar", self.texto())

    def test_conjunto_que_muda_entre_lotes_para_com_409(self):
        api = ApiOrfasFalsa(_chaves(450))
        purges = []

        def handler(req):
            if req.url.path.endswith("/orphans/purge"):
                purges.append(1)
                if len(purges) == 2:  # surge uma órfã sem o script saber
                    api.orfas.append("eu-products/surgiu-no-meio.webp")
            return api.handler(req)

        codigo = self.rodar(api, "--orfas", "--apagar", "--sim", handler=handler)
        self.assertEqual(codigo, 2)
        self.assertEqual(len(api.quarentena["2026-11-10"]), 200)
        self.assertIn("PAROU (409)", self.texto())
        self.assertEqual(self.csv_de("log-orfas-quarentena")[-1]["status"], "PAROU_409")

    def test_inventario_bloqueado_nao_move_nada(self):
        api = ApiOrfasFalsa(_chaves(3), bloqueado="varredura incompleta")
        self.assertEqual(self.rodar(api, "--orfas", "--apagar", "--sim"), 1)
        self.assertIn("BLOQUEADO", self.texto())
        self.assertFalse([c for c in api.chamadas if "purge" in c[1]])

    def test_conta_sem_permissao_de_plataforma(self):
        api = ApiOrfasFalsa(_chaves(1), permissao=False)
        self.assertEqual(self.rodar(api, "--orfas"), 1)
        self.assertIn("platform_admin", self.texto())

    def test_token_de_ambiente_precisa_ser_de_plataforma(self):
        api = ApiOrfasFalsa(_chaves(1))
        self.assertEqual(
            self.rodar(api, "--orfas", ambiente={"ILYA_TOKEN": _jwt({"market": "EU"})}), 1)
        self.assertIn("nao e de plataforma", self.texto())
        self.assertEqual(self.rodar(api, "--orfas", ambiente={"ILYA_TOKEN": api.novo_token()}), 0)

    def test_restaurar_devolve_o_lote(self):
        api = ApiOrfasFalsa([], quarentena={"2026-11-10": _chaves(3)})
        self.assertEqual(self.rodar(api, "--orfas", "--restaurar", "2026-11-10"), 0)
        self.assertEqual(api.orfas, _chaves(3))
        self.assertEqual(len(self.csv_de("log-orfas-restaurar")), 3)

    def test_restaurar_data_inexistente(self):
        api = ApiOrfasFalsa([], quarentena={"2026-11-10": _chaves(1)})
        self.assertEqual(self.rodar(api, "--orfas", "--restaurar", "2026-01-01"), 1)

    def test_esvaziar_quarentena_exige_texto_e_idade(self):
        api = ApiOrfasFalsa([], quarentena={"2026-11-10": _chaves(3)}, idade_dias=2)
        self.assertEqual(self.rodar(api, "--orfas", "--esvaziar-quarentena", "2026-11-10"), 1)
        self.assertIn("7+ dias", self.texto())
        self.assertEqual(len(api.quarentena["2026-11-10"]), 3)

        api = ApiOrfasFalsa([], quarentena={"2026-11-10": _chaves(3)})
        codigo = self.rodar(api, "--orfas", "--esvaziar-quarentena", "2026-11-10",
                            entradas=["admin", "APAGAR"])  # texto curto não basta
        self.assertEqual(codigo, 1)
        self.assertEqual(len(api.quarentena["2026-11-10"]), 3)

        codigo = self.rodar(api, "--orfas", "--esvaziar-quarentena", "2026-11-10",
                            entradas=["admin", "APAGAR DE VEZ"])
        self.assertEqual(codigo, 0)
        self.assertEqual(api.quarentena["2026-11-10"], [])
        self.assertEqual(len(self.csv_de("log-orfas-apagar-definitivo")), 3)

    def test_combinacoes_invalidas(self):
        api = ApiOrfasFalsa([])
        self.assertEqual(self.rodar(api, "--apagar"), 1)  # sem --orfas
        self.assertEqual(self.rodar(api, "--orfas", "--apply"), 1)
        self.assertEqual(self.rodar(api, "--orfas", "--apagar", "--quarentena"), 1)
        self.assertEqual(api.chamadas, [])

    def test_senha_e_token_nao_vazam_no_modo_orfas(self):
        api = ApiOrfasFalsa(_chaves(2))
        self.rodar(api, "--orfas", "--apagar", "--sim")
        texto = self.texto()
        for arquivo in self.saida.glob("*.csv"):
            texto += arquivo.read_text(encoding="utf-8-sig")
        self.assertNotIn(SENHA_FALSA, texto)
        for token in api.tokens:
            self.assertNotIn(token, texto)


if __name__ == "__main__":
    unittest.main()
