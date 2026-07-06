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
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
