FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p app/static/uploads && \
    addgroup --system ilya && \
    adduser --system --ingroup ilya ilya && \
    chown -R ilya:ilya /app

EXPOSE 8000
# O container inicia como root apenas para corrigir o ownership do volume do Railway
# (montado como root em runtime, o que quebrava o upload de fotos — Tópico 67.6),
# e imediatamente baixa o privilégio para `ilya` antes de subir a aplicação.
# As migrations são executadas pelo pre-deploy do Railway. O processo web
# inicia apenas depois que essa etapa termina com sucesso.
# find ! -user: só toca entradas com dono errado (mount point do volume e
# arquivos legados criados quando o container rodava como root) — barato em
# todo boot subsequente, ao contrário de um chown -R incondicional.
CMD ["/bin/sh", "-c", "find app/static/uploads ! -user ilya -exec chown ilya:ilya {} + && exec runuser -u ilya -- python startup.py serve"]
