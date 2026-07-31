from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.lib.colors import HexColor, black, white
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, HRFlowable
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY

# Cores do projeto
GOLD = HexColor('#8b6914')
DARK = HexColor('#2c2420')
LIGHT_BG = HexColor('#f8f6f2')
MUTED = HexColor('#6b5d52')
SUCCESS = HexColor('#16a34a')
WARNING = HexColor('#d97706')
DANGER = HexColor('#dc2626')
INFO = HexColor('#2563eb')

# Estilos
styles = getSampleStyleSheet()

title_style = ParagraphStyle(
    'CustomTitle', parent=styles['Title'], fontSize=24, textColor=GOLD,
    spaceAfter=6, fontName='Helvetica-Bold'
)

subtitle_style = ParagraphStyle(
    'CustomSubtitle', parent=styles['Normal'], fontSize=12, textColor=MUTED,
    spaceAfter=20, fontName='Helvetica'
)

heading1_style = ParagraphStyle(
    'Heading1Custom', parent=styles['Heading1'], fontSize=16, textColor=DARK,
    spaceBefore=20, spaceAfter=10, fontName='Helvetica-Bold'
)

heading2_style = ParagraphStyle(
    'Heading2Custom', parent=styles['Heading2'], fontSize=13, textColor=GOLD,
    spaceBefore=15, spaceAfter=8, fontName='Helvetica-Bold'
)

body_style = ParagraphStyle(
    'BodyCustom', parent=styles['Normal'], fontSize=10, textColor=DARK,
    spaceAfter=6, fontName='Helvetica', alignment=TA_JUSTIFY, leading=14
)

code_style = ParagraphStyle(
    'CodeCustom', parent=styles['Code'], fontSize=9, textColor=DARK,
    backColor=LIGHT_BG, borderWidth=1, borderColor=HexColor('#e8e0d6'),
    borderPadding=8, spaceAfter=10, fontName='Courier'
)

warning_style = ParagraphStyle(
    'WarningCustom', parent=body_style, backColor=HexColor('#fef3c7'),
    borderWidth=1, borderColor=WARNING, borderPadding=10, spaceAfter=10
)

danger_style = ParagraphStyle(
    'DangerCustom', parent=body_style, backColor=HexColor('#fee2e2'),
    borderWidth=1, borderColor=DANGER, borderPadding=10, spaceAfter=10
)

success_style = ParagraphStyle(
    'SuccessCustom', parent=body_style, backColor=HexColor('#dcfce7'),
    borderWidth=1, borderColor=SUCCESS, borderPadding=10, spaceAfter=10
)

info_style = ParagraphStyle(
    'InfoCustom', parent=body_style, backColor=HexColor('#dbeafe'),
    borderWidth=1, borderColor=INFO, borderPadding=10, spaceAfter=10
)

# Documento
doc = SimpleDocTemplate(
    "C:/Users/matheus.cardoso/Documents/Programador/Projeto Ilya/Alto Comando/Auditoria/otimizacao_pendente.pdf",
    pagesize=A4,
    rightMargin=2*cm, leftMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm
)

story = []

# Capa
story.append(Spacer(1, 3*cm))
story.append(Paragraph("Otimizacoes Pendentes", title_style))
story.append(Paragraph("Projeto Ilya — O que falta para o codigo estar otimizado", subtitle_style))
story.append(Spacer(1, 1*cm))
story.append(HRFlowable(width="100%", thickness=2, color=GOLD))
story.append(Spacer(1, 1*cm))

cover_data = [
    ["Projeto:", "Ilya — Sistema de Gestao de Pedidos"],
    ["Data:", "2026-07-16"],
    ["Auditor:", "MimoCode (mimo-auto)"],
    ["Score Atual:", "7/10 (qualidade do codigo)"],
    ["Score Meta:", "9/10"],
]
cover_table = Table(cover_data, colWidths=[4*cm, 12*cm])
cover_table.setStyle(TableStyle([
    ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
    ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
    ('FONTSIZE', (0, 0), (-1, -1), 10),
    ('TEXTCOLOR', (0, 0), (0, -1), GOLD),
    ('TEXTCOLOR', (1, 0), (1, -1), DARK),
    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
]))
story.append(cover_table)
story.append(PageBreak())

# Sumario
story.append(Paragraph("Sumario", heading1_style))
story.append(Spacer(1, 0.5*cm))
toc = [
    "1. Visao Geral do Problema",
    "2. Arquivos Monoliticos (CRITICO)",
    "3. Falta de Testes",
    "4. Codigo Duplicado",
    "5. O que ja esta bom",
    "6. Plano de Acao",
    "7. Prioridades",
]
for item in toc:
    story.append(Paragraph(item, body_style))
story.append(PageBreak())

# Secao 1
story.append(Paragraph("1. Visao Geral do Problema", heading1_style))
story.append(HRFlowable(width="100%", thickness=1, color=GOLD))
story.append(Spacer(1, 0.5*cm))

story.append(Paragraph("O codigo do Projeto Ilya e <b>funcional e seguro</b> (score 97/100 em seguranca), mas <b>nao esta otimizado para manutencao</b> (score 7/10 em qualidade).", body_style))
story.append(Spacer(1, 0.3*cm))

score_data = [
    ["Categoria", "Score", "Status"],
    ["Seguranca (Pentest)", "97/100", "EXCELENTE"],
    ["Frontend (impeccable)", "9/10", "EXCELENTE"],
    ["Backend (pos-alteracoes)", "96/100", "EXCELENTE"],
    ["Qualidade do Codigo", "7/10", "RAZOAVEL"],
]
score_table = Table(score_data, colWidths=[6*cm, 3*cm, 5*cm])
score_table.setStyle(TableStyle([
    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
    ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
    ('FONTSIZE', (0, 0), (-1, -1), 10),
    ('BACKGROUND', (0, 0), (-1, 0), GOLD),
    ('TEXTCOLOR', (0, 0), (-1, 0), white),
    ('BACKGROUND', (0, 1), (-1, 1), HexColor('#dcfce7')),
    ('BACKGROUND', (0, 2), (-1, 2), HexColor('#dcfce7')),
    ('BACKGROUND', (0, 3), (-1, 3), HexColor('#dcfce7')),
    ('BACKGROUND', (0, 4), (-1, 4), HexColor('#fef3c7')),
    ('GRID', (0, 0), (-1, -1), 0.5, HexColor('#e8e0d6')),
    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ('TOPPADDING', (0, 0), (-1, -1), 6),
    ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
]))
story.append(score_table)
story.append(Spacer(1, 0.5*cm))
story.append(Paragraph("<b>Resumo:</b> O sistema funciona e e seguro, mas o codigo e dificil de manter e expandir por causa de arquivos monoliticos e falta de testes.", body_style))
story.append(PageBreak())

# Secao 2
story.append(Paragraph("2. Arquivos Monoliticos (CRITICO)", heading1_style))
story.append(HRFlowable(width="100%", thickness=1, color=GOLD))
story.append(Spacer(1, 0.5*cm))

story.append(Paragraph("O principal problema sao arquivos com muitas linhas de codigo. O limite recomendado e 500 linhas por arquivo.", body_style))
story.append(Spacer(1, 0.3*cm))

mono_data = [
    ["Arquivo", "Linhas", "Limite", "Status"],
    ["CadastroPage.tsx", "2652", "500", "CRITICO"],
    ["OrcamentoPage.tsx", "1373", "500", "CRITICO"],
    ["PedidosPage.tsx", "1074", "500", "CRITICO"],
    ["orders.py", "978", "300", "ALTO"],
    ["import_csv.py", "852", "300", "ALTO"],
    ["auth.py", "551", "300", "MEDIO"],
]
mono_table = Table(mono_data, colWidths=[5*cm, 2.5*cm, 2.5*cm, 4*cm])
mono_table.setStyle(TableStyle([
    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
    ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
    ('FONTSIZE', (0, 0), (-1, -1), 9),
    ('BACKGROUND', (0, 0), (-1, 0), DANGER),
    ('TEXTCOLOR', (0, 0), (-1, 0), white),
    ('BACKGROUND', (0, 1), (-1, 3), HexColor('#fee2e2')),
    ('BACKGROUND', (0, 4), (-1, 5), HexColor('#fef3c7')),
    ('BACKGROUND', (0, 6), (-1, 6), HexColor('#fff7ed')),
    ('GRID', (0, 0), (-1, -1), 0.5, HexColor('#e8e0d6')),
    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ('TOPPADDING', (0, 0), (-1, -1), 5),
    ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
]))
story.append(mono_table)
story.append(Spacer(1, 0.5*cm))

story.append(Paragraph("<b>Problema especifico - CadastroPage.tsx (2652 linhas):</b>", heading2_style))
story.append(Paragraph("Este arquivo mistura 6 abas diferentes em um unico componente:", body_style))
story.append(Paragraph("• Aba Produtos (CRUD completo + upload de fotos)", body_style))
story.append(Paragraph("• Aba Clientes (CRUD + integracao ViaCEP)", body_style))
story.append(Paragraph("• Aba Representantes (CRUD + integracao ViaCEP)", body_style))
story.append(Paragraph("• Aba Opcionais (CRUD + upload de fotos)", body_style))
story.append(Paragraph("• Aba Tipos (CRUD simples)", body_style))
story.append(Paragraph("• Aba Importacao (CSV import)", body_style))
story.append(Spacer(1, 0.3*cm))
story.append(Paragraph("<b>Solucao:</b> Extrair cada aba para um componente separado:", code_style))
story.append(Paragraph("CadastroPage.tsx (100 linhas - so abas)<br/>├── ProdutosTab.tsx (~500 linhas)<br/>├── ClientesTab.tsx (~300 linhas)<br/>├── RepresentantesTab.tsx (~300 linhas)<br/>├── OpcionaisTab.tsx (~400 linhas)<br/>├── TiposTab.tsx (~200 linhas)<br/>└── ImportacaoTab.tsx (~200 linhas)", code_style))
story.append(PageBreak())

# Secao 3
story.append(Paragraph("3. Falta de Testes", heading1_style))
story.append(HRFlowable(width="100%", thickness=1, color=GOLD))
story.append(Spacer(1, 0.5*cm))

story.append(Paragraph("O projeto tem apenas 5 arquivos de teste no backend e nenhum no frontend.", body_style))
story.append(Spacer(1, 0.3*cm))

test_data = [
    ["Componente", "Testes", "Cobertura", "Status"],
    ["Backend (auth, orders)", "5 arquivos", "<5%", "INSUFICIENTE"],
    ["Frontend (componentes)", "0 arquivos", "0%", "AUSENTE"],
    ["Integracao (API)", "0 testes", "0%", "AUSENTE"],
    ["E2E (fluxos)", "0 testes", "0%", "AUSENTE"],
]
test_table = Table(test_data, colWidths=[5*cm, 3*cm, 3*cm, 4*cm])
test_table.setStyle(TableStyle([
    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
    ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
    ('FONTSIZE', (0, 0), (-1, -1), 9),
    ('BACKGROUND', (0, 0), (-1, 0), WARNING),
    ('TEXTCOLOR', (0, 0), (-1, 0), white),
    ('BACKGROUND', (0, 1), (-1, 4), HexColor('#fef3c7')),
    ('GRID', (0, 0), (-1, -1), 0.5, HexColor('#e8e0d6')),
    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ('TOPPADDING', (0, 0), (-1, -1), 5),
    ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
]))
story.append(test_table)
story.append(Spacer(1, 0.5*cm))
story.append(Paragraph("<b>O que falta testar:</b>", heading2_style))
story.append(Paragraph("• Fluxo de login/logout (autenticacao)", body_style))
story.append(Paragraph("• Criacao/edicao de pedidos (regra de negocio)", body_style))
story.append(Paragraph("• Calculo de desconto e IPI", body_style))
story.append(Paragraph("• Upload de fotos (validacao de magic bytes)", body_style))
story.append(Paragraph("• RBAC (permissoes por role)", body_style))
story.append(Paragraph("• Componentes React (formularios, tabelas)", body_style))
story.append(PageBreak())

# Secao 4
story.append(Paragraph("4. Codigo Duplicado", heading1_style))
story.append(HRFlowable(width="100%", thickness=1, color=GOLD))
story.append(Spacer(1, 0.5*cm))

story.append(Paragraph("Ha padroes de codigo que se repetem em multiplos arquivos:", body_style))
story.append(Spacer(1, 0.3*cm))

dup_data = [
    ["Padrao", "Ocorrencias", "Exemplo"],
    ["Formularios CRUD", "6x", "Cada aba tem create/update/delete similar"],
    ["Tabelas com sorting", "4x", "Logica de sorting repetida"],
    ["Modais de confirmacao", "3x", "Mesmo padrao de 'Tem certeza?'"],
    ["Toast sucesso/erro", "10x+", "toast.success()/toast.error()"],
]
dup_table = Table(dup_data, colWidths=[5*cm, 3*cm, 7*cm])
dup_table.setStyle(TableStyle([
    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
    ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
    ('FONTSIZE', (0, 0), (-1, -1), 9),
    ('BACKGROUND', (0, 0), (-1, 0), HexColor('#6366f1')),
    ('TEXTCOLOR', (0, 0), (-1, 0), white),
    ('BACKGROUND', (0, 1), (-1, -1), HexColor('#eef2ff')),
    ('GRID', (0, 0), (-1, -1), 0.5, HexColor('#e8e0d6')),
    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ('TOPPADDING', (0, 0), (-1, -1), 5),
    ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
]))
story.append(dup_table)
story.append(Spacer(1, 0.5*cm))
story.append(Paragraph("<b>Solucao:</b> Extrair hooks genericos:", code_style))
story.append(Paragraph("// hooks/useCrudTable.ts<br/>export function useCrudTable(fetcher, creator, updater, deleter) {<br/>  // Logica comum de tabela, sorting, paginacao<br/>}", code_style))
story.append(PageBreak())

# Secao 5
story.append(Paragraph("5. O que ja esta bom", heading1_style))
story.append(HRFlowable(width="100%", thickness=1, color=GOLD))
story.append(Spacer(1, 0.5*cm))

good_items = [
    ["Aspecto", "Status", "Observacao"],
    ["Seguranca", "97/100", "Argon2id, JWT, RBAC, LGPD completo"],
    ["Frontend Design", "9/10", "Design system impeccable implementado"],
    ["Backend Performance", "96/100", "GZip, cache, Redis, graceful shutdown"],
    ["React Query", "OK", "Cache invalidation funcionando"],
    ["Auth (token memoria)", "OK", "Cookie HttpOnly, refresh silencioso"],
    ["RBAC", "OK", "Multi-tenancy por rep_id/linked_id"],
    ["Logging", "OK", "Request ID, sem PII, estruturado"],
    ["Security Headers", "OK", "CSP, HSTS, X-Frame, X-XSS"],
    ["LGPD", "OK", "Acesso, exportacao, anonimizacao"],
]
good_table = Table(good_items, colWidths=[5*cm, 3*cm, 7*cm])
good_table.setStyle(TableStyle([
    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
    ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
    ('FONTSIZE', (0, 0), (-1, -1), 9),
    ('BACKGROUND', (0, 0), (-1, 0), SUCCESS),
    ('TEXTCOLOR', (0, 0), (-1, 0), white),
    ('BACKGROUND', (0, 1), (-1, -1), HexColor('#dcfce7')),
    ('GRID', (0, 0), (-1, -1), 0.5, HexColor('#e8e0d6')),
    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ('TOPPADDING', (0, 0), (-1, -1), 5),
    ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
]))
story.append(good_table)
story.append(PageBreak())

# Secao 6
story.append(Paragraph("6. Plano de Acao", heading1_style))
story.append(HRFlowable(width="100%", thickness=1, color=GOLD))
story.append(Spacer(1, 0.5*cm))

story.append(Paragraph("<b>Fase 1: Refatoracao dos Arquivos Monoliticos (Prioridade ALTA)</b>", heading2_style))
story.append(Paragraph("1. Dividir CadastroPage.tsx em 6 componentes (uma por aba)", body_style))
story.append(Paragraph("2. Dividir OrcamentoPage.tsx em componentes menores", body_style))
story.append(Paragraph("3. Dividir PedidosPage.tsx em componentes menores", body_style))
story.append(Paragraph("4. Dividir orders.py em services/ e routers/ menores", body_style))
story.append(Spacer(1, 0.3*cm))

story.append(Paragraph("<b>Fase 2: Extrair Codigo Duplicado (Prioridade MEDIA)</b>", heading2_style))
story.append(Paragraph("1. Criar hooks genericos (useCrudTable, useConfirmModal)", body_style))
story.append(Paragraph("2. Criar componentes reutilizaveis (ConfirmDialog, EmptyState)", body_style))
story.append(Paragraph("3. Padronizar toasts e erros", body_style))
story.append(Spacer(1, 0.3*cm))

story.append(Paragraph("<b>Fase 3: Adicionar Testes (Prioridade MEDIA)</b>", heading2_style))
story.append(Paragraph("1. Testes de integracao para auth (login, refresh, logout)", body_style))
story.append(Paragraph("2. Testes de integracao para orders (criacao, edicao, exclusao)", body_style))
story.append(Paragraph("3. Testes unitarios para logica de negocio (desconto, IPI)", body_style))
story.append(Paragraph("4. Testes de componente React (formularios, tabelas)", body_style))
story.append(PageBreak())

# Secao 7
story.append(Paragraph("7. Prioridades", heading1_style))
story.append(HRFlowable(width="100%", thickness=1, color=GOLD))
story.append(Spacer(1, 0.5*cm))

priority_data = [
    ["#", "Acao", "Esforco", "Impacto", "Prioridade"],
    ["1", "Dividir CadastroPage.tsx", "Alto", "Alto", "CRITICA"],
    ["2", "Dividir OrcamentoPage.tsx", "Medio", "Medio", "ALTA"],
    ["3", "Dividir PedidosPage.tsx", "Medio", "Medio", "ALTA"],
    ["4", "Testes de integracao (auth, orders)", "Medio", "Alto", "ALTA"],
    ["5", "Extrair hooks genericos", "Medio", "Medio", "MEDIA"],
    ["6", "Remover imports nao usados", "Baixo", "Baixo", "BAIXA"],
    ["7", "Mover magic numbers", "Baixo", "Baixo", "BAIXA"],
]
priority_table = Table(priority_data, colWidths=[1*cm, 6*cm, 2.5*cm, 2.5*cm, 3*cm])
priority_table.setStyle(TableStyle([
    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
    ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
    ('FONTSIZE', (0, 0), (-1, -1), 9),
    ('BACKGROUND', (0, 0), (-1, 0), DARK),
    ('TEXTCOLOR', (0, 0), (-1, 0), white),
    ('BACKGROUND', (0, 1), (-1, 1), HexColor('#fee2e2')),
    ('BACKGROUND', (0, 2), (-1, 3), HexColor('#fef3c7')),
    ('BACKGROUND', (0, 4), (-1, 5), HexColor('#fef3c7')),
    ('BACKGROUND', (0, 6), (-1, 7), HexColor('#f0f9ff')),
    ('GRID', (0, 0), (-1, -1), 0.5, HexColor('#e8e0d6')),
    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ('TOPPADDING', (0, 0), (-1, -1), 5),
    ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
]))
story.append(priority_table)
story.append(Spacer(1, 1*cm))
story.append(HRFlowable(width="100%", thickness=2, color=GOLD))
story.append(Spacer(1, 0.5*cm))
story.append(Paragraph("Documento gerado por MimoCode — Auditor do Projeto Ilya", subtitle_style))

doc.build(story)
print("PDF gerado com sucesso!")
