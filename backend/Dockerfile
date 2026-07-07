FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p app/static/uploads && \
    addgroup --system ilya && \
    adduser --system --ingroup ilya ilya && \
    chown -R ilya:ilya /app

USER ilya

EXPOSE 8000
# alembic upgrade + seed_admin são idempotentes — seguros de rodar a cada start
# (seed_admin exige ADMIN_EMAIL/ADMIN_PASSWORD e não faz nada se o admin já existir).
CMD alembic upgrade head && python seed_admin.py && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
