"""Testes do importador de TECIDO FORNECIDO (API simulada, planilha sintetica)."""
import base64
import csv
import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
import importar_tecido_fornecido as imp  # noqa: E402
from trocar_fotos_eu import ErroFatal  # noqa: E402


def _xlsx(caminho: Path, linhas: list[list]) -> None:
    """Monta um .xlsx minimo (textos em sharedStrings, numeros em <v>)."""
    textos: list[str] = []

    def celula(ref: str, valor) -> str:
        if isinstance(valor, str):
            textos.append(valor)
            return f'<c r="{ref}" t="s"><v>{len(textos) - 1}</v></c>'
        return f'<c r="{ref}"><v>{valor}</v></c>'

    corpo = "".join(
        f'<row r="{i}">' + "".join(celula(f"{chr(65 + j)}{i}", v) for j, v in enumerate(linha)) + "</row>"
        for i, linha in enumerate(linhas, start=1)
    )
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    with zipfile.ZipFile(caminho, "w") as pacote:
        pacote.writestr("xl/worksheets/sheet1.xml", f'<worksheet {ns}><sheetData>{corpo}</sheetData></worksheet>')
        pacote.writestr("xl/sharedStrings.xml", f'<sst {ns}>' + "".join(f"<si><t>{t}</t></si>" for t in textos) + "</sst>")


CABECALHO = ["COD", "PVP", "LOJISTA", "ARQUITETO", "CORPORATIVO", "MTS TECIDO "]
RESPOSTA = {
    "market": "EU", "currency": "EUR", "dry_run": True, "rows_in_file": 2,
    "to_create": ["AA0001"], "to_update": [{"sku": "AA0002", "changes": {"price_pvp": {"from": "1.00", "to": "2.00"}}}],
    "unchanged": [], "unknown_skus": ["ZZ9999"], "without_fabric_application": ["AA0001"], "applied": 0, "errors": [],
}


class ImportadorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self.chamadas: list[httpx.Request] = []

    def _client(self, resposta=RESPOSTA, status=200) -> httpx.Client:
        def handler(request: httpx.Request) -> httpx.Response:
            self.chamadas.append(request)
            if request.url.path.endswith("/platform/auth/login"):
                # JWT de plataforma sintetico (sem assinatura): {"scope":"platform"}
                corpo = base64.urlsafe_b64encode(json.dumps({"scope": "platform"}).encode()).decode().rstrip("=")
                return httpx.Response(200, json={"access_token": f"x.{corpo}.y"})
            return httpx.Response(status, json=resposta)

        return httpx.Client(transport=httpx.MockTransport(handler))

    def _rodar(self, argv, confirmacao="", **kw) -> tuple[int, list[str]]:
        saida: list[str] = []
        codigo = imp.main(
            argv, client=self._client(**kw),
            entrada=lambda pergunta: confirmacao if "Digite" in pergunta else "admin", senha=lambda _: "x",
            imprimir=saida.append, ambiente={},
        )
        return codigo, saida

    def _envios(self) -> list[str]:
        return [c.url.params["dry_run"] for c in self.chamadas if "supplied-fabric" in c.url.path]

    def test_le_xlsx_e_gera_csv_com_o_cabecalho_da_planilha(self) -> None:
        arquivo = self.dir / "p.xlsx"
        _xlsx(arquivo, [CABECALHO, ["SF0343", 5710.98, 2855.49, 3712.137, 4283.235, 13.2], ["PL0168", 1.5, 1, 1, 1, 4.8]])
        conteudo, dados = imp.montar_csv(imp.ler_arquivo(arquivo))
        linhas = list(csv.reader(io.StringIO(conteudo.decode()), delimiter=";"))
        self.assertEqual(dados, 2)
        self.assertEqual(linhas[0], imp.COLUNAS)
        self.assertEqual(linhas[1], ["SF0343", "5710.98", "2855.49", "3712.137", "4283.235", "13.2"])

    def test_planilha_sem_coluna_obrigatoria_e_recusada(self) -> None:
        with self.assertRaises(ErroFatal):
            imp.montar_csv([["COD", "PVP"], ["A", "1"]])

    def test_dry_run_envia_dry_run_true_e_nao_grava(self) -> None:
        arquivo = self.dir / "p.xlsx"
        _xlsx(arquivo, [CABECALHO, ["AA0001", 1, 1, 1, 1, 1]])
        codigo, saida = self._rodar([str(arquivo), "--saida", str(self.dir / "out")])
        self.assertEqual(codigo, 0)
        self.assertEqual(self._envios(), ["true"])
        self.assertTrue(any("Nada foi gravado" in linha for linha in saida))
        relatorio = next((self.dir / "out").glob("relatorio-dry-run-*.csv")).read_text(encoding="utf-8-sig")
        self.assertIn("AA0001;CRIAR", relatorio)
        self.assertIn("ZZ9999;IGNORADO_NAO_EXISTE_NO_EU", relatorio)
        self.assertIn("AVISO_SEM_APLICACAO_TECIDOS_IBTW", relatorio)

    def test_apply_pede_confirmacao_e_so_grava_depois(self) -> None:
        arquivo = self.dir / "p.xlsx"
        _xlsx(arquivo, [CABECALHO, ["AA0001", 1, 1, 1, 1, 1]])
        codigo, _ = self._rodar([str(arquivo), "--apply", "--saida", str(self.dir / "out")], confirmacao="nao")
        self.assertEqual(codigo, 1)
        self.assertEqual(self._envios(), ["true"])  # nada foi gravado
        self.chamadas.clear()
        codigo, _ = self._rodar([str(arquivo), "--apply", "--saida", str(self.dir / "out")], confirmacao=imp.CONFIRMACAO)
        self.assertEqual(codigo, 0)
        self.assertEqual(self._envios(), ["true", "false"])

    def test_api_recusa_arquivo_com_422(self) -> None:
        arquivo = self.dir / "p.xlsx"
        _xlsx(arquivo, [CABECALHO, ["AA0001", "abc", 1, 1, 1, 1]])
        codigo, saida = self._rodar(
            [str(arquivo)], status=422, resposta={"detail": {"errors": ["Linha 2 (AA0001): preço inválido"]}},
        )
        self.assertEqual(codigo, 1)
        self.assertTrue(any("Linha 2" in linha for linha in saida))


if __name__ == "__main__":
    unittest.main()
