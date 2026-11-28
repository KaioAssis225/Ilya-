#!/usr/bin/env bash
# Passo 3 do RUNBOOK-virada.md: troca os dados da stack /opt/ilya-production pelas cópias
# novas (ilya_copy_* em ilya-railway-copy-db e estoque_copy_* em ilya-estoque-pg).
#
#   cd /opt/ilya-production
#   bash swap_data.sh <ilya_copy_...> <estoque_copy_...>
#
# Mede o tempo de cada etapa (a soma, mais as cópias do passo 2, é a janela com as
# gravações pausadas). NÃO apaga nada: restaura em bancos NOVOS (ilya_new/estoque_new;
# se já existirem, para), confere as contagens contra a cópia e só então renomeia. Os
# bancos que estavam em uso viram ilya_ensaio_<carimbo>/estoque_ensaio_<carimbo> e ficam
# de reserva (remover é decisão do responsável). Se algo falhar antes da troca, nada mudou.
set -euo pipefail

ILYA_COPY=${1:?uso: swap_data.sh <banco-ilya_copy> <banco-estoque_copy>}
ESTOQUE_COPY=${2:?uso: swap_data.sh <banco-ilya_copy> <banco-estoque_copy>}
STAMP=$(date -u +%Y%m%d_%H%M%S)

stage() { START=$(date +%s); CURRENT=$1; echo "== $1"; }
done_stage() { printf '   [%5ss] %s\n' "$(( $(date +%s) - START ))" "$CURRENT"; }

# Contagem de linhas de todas as tabelas de public (ordenada), para comparar origem x destino.
COUNT_SQL="SELECT relname || ' = ' || (xpath('/row/c/text()', query_to_xml(format('SELECT count(*) AS c FROM public.%I', relname), false, true, '')))[1]::text FROM pg_class WHERE relkind='r' AND relnamespace='public'::regnamespace ORDER BY relname"

restore_one() { # <serviço compose> <container origem> <banco origem> <role app> <banco final>
  local svc=$1 src=$2 srcdb=$3 role=$4 final=$5
  docker compose exec -T "$svc" psql -U postgres -X -q -v ON_ERROR_STOP=1 \
    -c "CREATE DATABASE ${final}_new OWNER ${role}"
  docker compose exec -T "$svc" psql -U postgres -d "${final}_new" -X -q -v ON_ERROR_STOP=1 \
    -c "CREATE EXTENSION IF NOT EXISTS pg_trgm"
  docker exec "$src" pg_dump -U postgres -d "$srcdb" --no-owner --no-acl \
    | grep -v -E '^(COMMENT ON EXTENSION|CREATE EXTENSION)' \
    | docker compose exec -T "$svc" psql -U "$role" -d "${final}_new" -X -q \
        -v ON_ERROR_STOP=1 --single-transaction >/dev/null
}

compare_counts() { # <serviço> <container origem> <banco origem> <banco novo>
  local a b
  a=$(docker exec "$2" psql -U postgres -d "$3" -X -At -c "$COUNT_SQL")
  b=$(docker compose exec -T "$1" psql -U postgres -d "$4" -X -At -c "$COUNT_SQL")
  if [ "$a" != "$b" ]; then
    echo "CONTAGENS DIFERENTES entre $3 e $4:" >&2; diff <(echo "$a") <(echo "$b") >&2 || true; exit 1
  fi
  echo "   contagens iguais em $(echo "$a" | wc -l) tabelas ($4)"
}

TOTAL_START=$(date +%s)

stage "1. parar APIs e workers da stack (Ilya e Estoque)"
docker compose stop ilya-api ilya-email-worker estoque-api estoque-worker >/dev/null
done_stage

stage "2. restaurar o Ilya em ilya_new"
restore_one ilya-db ilya-railway-copy-db "$ILYA_COPY" ilya_app ilya
done_stage

stage "3. restaurar o Estoque em estoque_new"
restore_one estoque-db ilya-estoque-pg "$ESTOQUE_COPY" estoque_app estoque
done_stage

stage "4. conferir contagens (cópia x banco novo)"
compare_counts ilya-db ilya-railway-copy-db "$ILYA_COPY" ilya_new
compare_counts estoque-db ilya-estoque-pg "$ESTOQUE_COPY" estoque_new
done_stage

stage "5. trocar os nomes (o banco em uso vira *_ensaio_$STAMP)"
docker compose exec -T ilya-db psql -U postgres -d postgres -X -q -v ON_ERROR_STOP=1 \
  -c "ALTER DATABASE ilya RENAME TO ilya_ensaio_$STAMP" -c "ALTER DATABASE ilya_new RENAME TO ilya"
docker compose exec -T estoque-db psql -U postgres -d postgres -X -q -v ON_ERROR_STOP=1 \
  -c "ALTER DATABASE estoque RENAME TO estoque_ensaio_$STAMP" -c "ALTER DATABASE estoque_new RENAME TO estoque"
done_stage

stage "6. roles e GRANTs (bootstrap_roles.py roles/grants/verify)"
python3 bootstrap_roles.py roles >/dev/null && python3 bootstrap_roles.py grants >/dev/null
python3 bootstrap_roles.py verify | tail -2
done_stage

stage "7. subir a stack (as migrações rodam sobre o banco restaurado)"
docker compose up -d --wait --wait-timeout 300 >/dev/null
done_stage
docker compose ps --format '   {{.Service}} {{.Status}}'
echo "   migrações:"
for s in ilya-migrate estoque-migrate; do
  docker compose logs --no-log-prefix --tail 3 "$s" 2>/dev/null | sed 's/^/     /'
done

echo
echo "== Total desta rotina (sem as cópias do passo 2, medidas pelos scripts de cópia): $(( $(date +%s) - TOTAL_START ))s"
echo "   bancos de reserva (não removidos): ilya_ensaio_$STAMP e estoque_ensaio_$STAMP"
