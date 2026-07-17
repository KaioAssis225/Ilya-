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
# alembic upgrade + seed_admin são idempotentes — seguros de rodar a cada start
# (seed_admin exige ADMIN_EMAIL/ADMIN_PASSWORD e não faz nada se o admin já existir).
# find ! -user: só toca entradas com dono errado (mount point do volume e
# arquivos legados criados quando o container rodava como root) — barato em
# todo boot subsequente, ao contrário de um chown -R incondicional.
CMD find app/static/uploads ! -user ilya -exec chown ilya:ilya {} + && \
    exec runuser -u ilya -- python startup.py
