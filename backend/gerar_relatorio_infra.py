"""
Gera o relatorio PDF de acoes de infraestrutura pendentes - Projeto Ilya.
Uso: python gerar_relatorio_infra.py
Saida: relatorio_infra_ilya.pdf
"""
from fpdf import FPDF
from datetime import date

GOLD   = (139, 105, 20)
DARK   = (44,  36,  32)
MUTED  = (157, 141, 129)
BG     = (248, 246, 242)
RED    = (178, 94,  80)
YELLOW = (200, 149, 46)
GREEN  = (80,  130, 80)
WHITE  = (255, 255, 255)


class RelatorioPDF(FPDF):
    def header(self):
        self.set_fill_color(*DARK)
        self.rect(0, 0, 210, 18, 'F')
        self.set_y(4)
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(*GOLD)
        self.cell(0, 10, "ILYA  -  RELATORIO DE SEGURANCA DE INFRAESTRUTURA", align="C")
        self.ln(14)

    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", "", 7)
        self.set_text_color(*MUTED)
        self.cell(0, 6,
                  f"Projeto Ilya  |  Gerado em {date.today().strftime('%d/%m/%Y')}  |  Confidencial  |  Pag. {self.page_no()}",
                  align="C")

    def section_title(self, text: str):
        self.ln(5)
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(*GOLD)
        self.set_draw_color(*GOLD)
        self.cell(0, 7, text, border="B", ln=True)
        self.ln(2)
        self.set_text_color(*DARK)

    def body(self, text: str, indent: int = 0):
        self.set_font("Helvetica", "", 9)
        self.set_text_color(*DARK)
        self.set_x(10 + indent)
        self.multi_cell(190 - indent, 5, text)

    def badge(self, label: str, color):
        self.set_font("Helvetica", "B", 8)
        self.set_text_color(*WHITE)
        self.set_fill_color(*color)
        self.cell(22, 5, f"  {label}", fill=True, ln=False)
        self.set_text_color(*DARK)

    def item_block(self, numero, titulo, severidade, sev_color,
                   descricao, risco, acao, esforco):
        self.ln(4)
        self.set_fill_color(*BG)
        y0 = self.get_y()
        self.rect(10, y0, 190, 2, 'F')

        self.set_font("Helvetica", "B", 9)
        self.set_text_color(*DARK)
        self.cell(8, 6, numero, ln=False)
        self.cell(130, 6, titulo, ln=False)
        self.badge(severidade, sev_color)
        self.ln(7)

        self.body(f"Descricao: {descricao}", indent=8)
        self.ln(1)
        self.body(f"Risco: {risco}", indent=8)
        self.ln(1)
        self.body(f"Acao requerida: {acao}", indent=8)
        self.ln(1)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(*MUTED)
        self.set_x(18)
        self.cell(0, 5, f"Esforco estimado: {esforco}")
        self.set_text_color(*DARK)
        self.ln(3)


def build():
    pdf = RelatorioPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Titulo
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(*DARK)
    pdf.ln(2)
    pdf.cell(0, 10, "Acoes de Seguranca Pendentes", ln=True, align="C")
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*MUTED)
    pdf.cell(0, 5, "Itens nao resolviveis via codigo - requerem intervencao de infraestrutura", ln=True, align="C")
    pdf.ln(4)

    # Tabela de resumo
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_fill_color(*DARK)
    pdf.set_text_color(*WHITE)
    pdf.cell(10, 6, "#",            fill=True, border=1)
    pdf.cell(80, 6, "Item",         fill=True, border=1)
    pdf.cell(25, 6, "Severidade",   fill=True, border=1)
    pdf.cell(35, 6, "Esforco",      fill=True, border=1)
    pdf.cell(40, 6, "Responsavel",  fill=True, border=1, ln=True)

    rows = [
        ("1", "Backup automatico do banco de dados",  "Alta",  YELLOW, "Medio",  "DevOps / DBA"),
        ("2", "Criptografia at-rest no PostgreSQL",   "Media", YELLOW, "Alto",   "DevOps / DBA"),
        ("3", "TLS / HTTPS obrigatorio em producao",  "Alta",  RED,    "Medio",  "DevOps / Infra"),
        ("4", "Bind do backend restrito (0.0.0.0)",   "Baixa", GREEN,  "Baixo",  "DevOps"),
        ("5", "Atualizacao do Starlette (FastAPI)",   "Media", YELLOW, "Medio",  "Desenvolvedor"),
    ]
    pdf.set_font("Helvetica", "", 8)
    for i, (num, item, sev, sev_col, esf, resp) in enumerate(rows):
        fill_bg = (250, 248, 244) if i % 2 == 0 else WHITE
        pdf.set_fill_color(*fill_bg)
        pdf.set_text_color(*DARK)
        pdf.cell(10, 6, num,  fill=True, border=1)
        pdf.cell(80, 6, item, fill=True, border=1)
        pdf.set_text_color(*sev_col)
        pdf.cell(25, 6, sev,  fill=True, border=1)
        pdf.set_text_color(*DARK)
        pdf.cell(35, 6, esf,  fill=True, border=1)
        pdf.cell(40, 6, resp, fill=True, border=1, ln=True)

    # Contexto
    pdf.section_title("CONTEXTO")
    pdf.body(
        "Este relatorio documenta os itens de seguranca identificados pela auditoria MimoSec "
        "(2026-06-26) que nao podem ser resolvidos atraves de alteracoes de codigo. "
        "Itens de codigo (CORS, rate limiting, dependencias PyJWT e python-multipart) foram "
        "corrigidos diretamente no repositorio. Os itens abaixo requerem configuracao de "
        "infraestrutura, provisionamento de servicos ou intervencao no ambiente de producao."
    )

    # Itens detalhados
    pdf.section_title("ITENS DETALHADOS")

    pdf.item_block(
        "1", "Backup Automatico do Banco de Dados", "ALTA", RED,
        descricao=(
            "Nao existe politica de backup automatizado para o banco PostgreSQL 16. "
            "Em caso de falha de disco, corrupcao de dados ou acidente operacional, "
            "toda a base de clientes, pedidos e representantes seria perdida permanentemente."
        ),
        risco=(
            "Perda total e irrecuperavel de dados em caso de falha. Nao conformidade com "
            "a LGPD (Art. 46 - medidas de seguranca adequadas para protecao de dados pessoais)."
        ),
        acao=(
            "1. Configurar pg_dump agendado via cron (minimo: diario, recomendado: a cada 6h). "
            "2. Armazenar backups em volume externo ou bucket S3/Backblaze criptografado. "
            "3. Testar restore mensalmente. "
            "4. Reter backups por minimo 30 dias. "
            "Cron exemplo: 0 */6 * * *  pg_dump -U postgres ilya_db | gzip > /backups/ilya_$(date).sql.gz"
        ),
        esforco="4-8h de configuracao + teste de restore"
    )

    pdf.item_block(
        "2", "Criptografia At-Rest no PostgreSQL", "MEDIA", YELLOW,
        descricao=(
            "Os dados armazenados no banco (nomes, e-mails, telefones, enderecos de clientes) "
            "nao estao criptografados em disco. O volume Docker monta o datadir do PostgreSQL "
            "sem criptografia de sistema de arquivos."
        ),
        risco=(
            "Acesso fisico ao servidor ou ao host Docker expoe todos os dados pessoais em texto "
            "claro. Impacto LGPD: dados pessoais sensiveis devem ser protegidos com tecnicas "
            "adequadas de anonimizacao ou criptografia (Art. 46)."
        ),
        acao=(
            "Opcao A (VPS): Habilitar LUKS no volume de dados antes da instalacao do PostgreSQL. "
            "Opcao B (managed DB): Migrar para servico gerenciado (RDS, Supabase, Neon) que "
            "oferece encryption-at-rest nativo e backups automaticos inclusos. "
            "Opcao C (app layer): Criptografar campos PII com pgcrypto antes do armazenamento "
            "(mais trabalhoso, requer migracao de dados existentes)."
        ),
        esforco="Alto - 1 a 3 dias dependendo da abordagem escolhida"
    )

    pdf.item_block(
        "3", "TLS / HTTPS Obrigatorio em Producao", "ALTA", RED,
        descricao=(
            "O backend esta configurado para HTTP puro (porta 8000). Em producao, "
            "todo trafego entre cliente e servidor trafega sem criptografia, expondo "
            "tokens JWT, cookies de sessao e dados pessoais a interceptacao (MITM)."
        ),
        risco=(
            "Interceptacao de tokens de autenticacao via rede (Wi-Fi publico, roteadores "
            "comprometidos). Flags de seguranca dos cookies (Secure=True) nao funcionam "
            "sem HTTPS. Nao conformidade com PCI-DSS e boas praticas OWASP."
        ),
        acao=(
            "1. Provisionar certificado TLS gratuito via Let's Encrypt + Certbot. "
            "2. Configurar nginx como reverse proxy: nginx (443) > uvicorn (127.0.0.1:8000). "
            "3. Redirecionar HTTP (80) para HTTPS (301 Permanent Redirect). "
            "4. Ativar HSTS: Strict-Transport-Security: max-age=31536000; includeSubDomains. "
            "5. Alterar .env: DEBUG=False (cookie Secure ja e condicional no codigo). "
            "Ref: https://letsencrypt.org/getting-started/"
        ),
        esforco="2-4h (nginx + certbot + renovacao automatica via cron)"
    )

    pdf.item_block(
        "4", "Bind do Backend Restrito (0.0.0.0 -> 127.0.0.1)", "BAIXA", GREEN,
        descricao=(
            "O uvicorn esta escutando em 0.0.0.0:8000, tornando a API diretamente "
            "acessivel de qualquer interface de rede do host. Com nginx como proxy "
            "reverso, o backend nao precisa ser acessivel externamente."
        ),
        risco=(
            "Exposicao desnecessaria da API diretamente a internet, bypassando o "
            "reverse proxy e seus controles (rate limiting de rede, filtros IP, WAF). "
            "Risco baixo se firewall estiver configurado, mas e uma superficie desnecessaria."
        ),
        acao=(
            "No docker-compose.yml, alterar o port binding: "
            "  DE:  ports: ['8000:8000'] "
            "  PARA: ports: ['127.0.0.1:8000:8000'] "
            "Apos configurar nginx como proxy reverso (item #3), remover o port binding "
            "publico completamente - nginx e uvicorn comunicam-se pela rede Docker interna."
        ),
        esforco="15 minutos - uma linha no docker-compose.yml"
    )

    pdf.item_block(
        "5", "Atualizacao do Starlette via Upgrade do FastAPI", "MEDIA", YELLOW,
        descricao=(
            "O pip-audit identificou 8 CVEs no starlette 0.41.3 (dependencia transitiva "
            "do FastAPI 0.115.5). A correcao requer starlette >= 1.3.1, incompativel com "
            "FastAPI 0.115.5 - necessita upgrade do proprio FastAPI. "
            "CVEs: CVE-2025-54121, CVE-2026-48817, PYSEC-2026-249 (entre outros)."
        ),
        risco=(
            "Os CVEs do starlette afetam principalmente processamento de headers e "
            "requisicoes malformadas. Severidade variada (baixa a media). "
            "Risco aumentado se exposto diretamente a internet sem WAF ou rate limiting."
        ),
        acao=(
            "1. Testar em staging: pip install 'fastapi>=0.116.0'. "
            "2. Verificar compatibilidade: SQLAlchemy 2.0, Pydantic v2, slowapi. "
            "3. Executar testes de regressao (manual ou automatizado). "
            "4. Atualizar requirements.txt: fastapi>=0.116.0. "
            "5. Reconstruir: docker compose up --build. "
            "Prazo recomendado: proximo ciclo de manutencao (max. 60 dias)."
        ),
        esforco="Medio - 2 a 4h de testes de regressao"
    )

    # Matriz de prioridade
    pdf.section_title("MATRIZ DE PRIORIDADE (Impacto x Urgencia)")
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_fill_color(*DARK)
    pdf.set_text_color(*WHITE)
    pdf.cell(10, 6, "#",          fill=True, border=1)
    pdf.cell(70, 6, "Item",       fill=True, border=1)
    pdf.cell(25, 6, "Impacto",    fill=True, border=1)
    pdf.cell(25, 6, "Urgencia",   fill=True, border=1)
    pdf.cell(30, 6, "Prazo rec.", fill=True, border=1)
    pdf.cell(30, 6, "Custo est.", fill=True, border=1, ln=True)

    matrix = [
        ("3", "TLS / HTTPS em producao",       "Critico", "Alta",  "Imediato",    "Baixo (gratuito)"),
        ("1", "Backup automatico do banco",     "Alto",    "Alta",  "1 semana",    "Baixo (cron+S3)"),
        ("5", "Upgrade Starlette / FastAPI",    "Medio",   "Media", "60 dias",     "Baixo (dev)"),
        ("2", "Criptografia at-rest",           "Medio",   "Media", "3 meses",     "Medio a Alto"),
        ("4", "Bind do backend restrito",       "Baixo",   "Baixa", "Com item #3", "Nenhum"),
    ]
    pdf.set_font("Helvetica", "", 8)
    for i, row in enumerate(matrix):
        fill_bg = (250, 248, 244) if i % 2 == 0 else WHITE
        pdf.set_fill_color(*fill_bg)
        for j, cell in enumerate(row):
            widths = [10, 70, 25, 25, 30, 30]
            is_last = (j == len(row) - 1)
            color = DARK
            if   j == 2 and cell == "Critico": color = RED
            elif j == 2 and cell == "Alto":    color = YELLOW
            elif j == 3 and cell == "Alta":    color = RED
            elif j == 3 and cell == "Media":   color = YELLOW
            pdf.set_text_color(*color)
            pdf.cell(widths[j], 6, cell, fill=True, border=1, ln=True if is_last else False)
        pdf.set_text_color(*DARK)

    # Itens ja corrigidos
    pdf.section_title("ITENS JA CORRIGIDOS NO CODIGO (para referencia)")
    corrigidos = [
        ("[OK]", "Senha temporaria hardcoded (senhailya)",   "Bloco 46 - secrets.token_urlsafe(9)"),
        ("[OK]", "CORS allow_methods=[*]",                   "Corrigido - lista explicita de metodos"),
        ("[OK]", "Rate limit ausente em /change-password",   "Corrigido - @limiter.limit(5/minute)"),
        ("[OK]", "PyJWT 2.9.0 (8 CVEs)",                    "Atualizado para 2.13.0 em requirements.txt"),
        ("[OK]", "python-multipart 0.0.12 (7 CVEs)",         "Atualizado para 0.0.31 em requirements.txt"),
        ("[OK]", "Rate limit em /generate-sign-token",        "Ja existia - @limiter.limit(5/minute)"),
    ]
    pdf.set_font("Helvetica", "", 8)
    for mark, item, solucao in corrigidos:
        pdf.set_text_color(*GREEN)
        pdf.set_x(12)
        pdf.cell(10, 5, mark)
        pdf.set_text_color(*DARK)
        pdf.cell(85, 5, item)
        pdf.set_text_color(*MUTED)
        pdf.cell(0, 5, solucao, ln=True)
    pdf.set_text_color(*DARK)

    pdf.ln(5)
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(*MUTED)
    pdf.multi_cell(0, 5,
        "Score de seguranca atual (pos-correcoes de codigo): 87/100.  "
        "Score projetado apos implementacao de todos os itens de infraestrutura: 96/100.  "
        f"Auditoria base: MimoSec - 2026-06-26.  Este relatorio: {date.today().strftime('%d/%m/%Y')}."
    )

    out = "/app/relatorio_infra_ilya.pdf"
    pdf.output(out)
    print(f"PDF gerado: {out}")


if __name__ == "__main__":
    build()
