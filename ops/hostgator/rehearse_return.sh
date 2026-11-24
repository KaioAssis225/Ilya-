#!/usr/bin/env bash
# Ensaio do CAMINHO DE VOLTA (RUNBOOK-virada.md): leva o que foi gravado na VPS de volta a
# um Postgres, medindo cada etapa. O destino aqui é DESCARTÁVEL e fica na própria VPS
# (rede Docker interna, sem portas, sem senha). Nunca aponta para o Railway.
#
#   cd /opt/ilya-production
#   bash rehearse_return.sh
#
# Faz: para APIs/workers (congela as gravações) -> pg_dump -Fc dos dois bancos em uso ->
# sobe Postgres 18 e 16 descartáveis -> restaura com o cliente 18 (--no-owner --no-acl,
# como seria no Railway) -> confere contagens contra o banco em uso -> religa a stack.
# O Postgres 16 prova o pior caso (servidor de destino mais antigo que o dump).
# NÃO remove nada ao final: containers, rede e arquivos criados aqui ficam até o
# responsável autorizar a remoção (a lista é impressa no fim).
set -euo pipefail

DIR=/opt/ilya-production/return-rehearsal
NET=ilya-return-net
IMG18=postgres:18-alpine
mkdir -p "$DIR"; chmod 700 "$DIR"

stage() { START=$(date +%s); CURRENT=$1; echo "== $1"; }
done_stage() { printf '   [%5ss] %s\n' "$(( $(date +%s) - START ))" "$CURRENT"; }

COUNT_SQL="SELECT relname || ' = ' || (xpath('/row/c/text()', query_to_xml(format('SELECT count(*) AS c FROM public.%I', relname), false, true, '')))[1]::text FROM pg_class WHERE relkind='r' AND relnamespace='public'::regnamespace ORDER BY relname"

TOTAL_START=$(date +%s)
# Se qualquer etapa falhar, a stack do ensaio volta a subir (não fica parada).
trap 'docker compose up -d >/dev/null 2>&1 || true' EXIT

stage "1. parar APIs e workers (congelar as gravações)"
docker compose stop ilya-api ilya-email-worker estoque-api estoque-worker >/dev/null
done_stage

stage "2. dump consistente dos dois bancos em uso (pg_dump -Fc)"
docker compose exec -T ilya-db pg_dump -U postgres -d ilya -Fc --no-owner --no-acl > "$DIR/ilya.dump"
docker compose exec -T estoque-db pg_dump -U postgres -d estoque -Fc --no-owner --no-acl > "$DIR/estoque.dump"
chmod 600 "$DIR"/*.dump
ls -lh "$DIR"/*.dump | awk '{print "   " $5 "  " $9}'
done_stage

stage "3. subir os Postgres descartáveis (18 e 16), rede interna, sem portas"
docker network inspect "$NET" >/dev/null 2>&1 || docker network create --internal "$NET" >/dev/null
for v in 18 16; do
  docker run -d --name "ilya-return-pg$v" --network "$NET" -e POSTGRES_HOST_AUTH_METHOD=trust \
    "postgres:$v-alpine" >/dev/null
done
for v in 18 16; do
  until docker exec "ilya-return-pg$v" pg_isready -U postgres >/dev/null 2>&1; do sleep 1; done
done
sleep 3   # a imagem reinicia uma vez depois do initdb
for v in 18 16; do
  until docker exec "ilya-return-pg$v" pg_isready -U postgres >/dev/null 2>&1; do sleep 1; done
done
done_stage

restore_into() { # <versão> <nome do banco> <arquivo>
  docker exec "ilya-return-pg$1" createdb -U postgres "$2"
  if [ "$1" -ge 17 ]; then
    docker run --rm -i --network "$NET" "$IMG18" pg_restore -h "ilya-return-pg$1" -U postgres -d "$2" \
      --no-owner --no-acl --single-transaction --exit-on-error < "$3"
  else
    # Servidor mais antigo que o dump: o pg_restore 18 emite "SET transaction_timeout" (novo
    # no PG17) e o servidor recusa. Medido no ensaio: sem este filtro o restore falha.
    docker run --rm -i --network "$NET" "$IMG18" pg_restore --no-owner --no-acl -f - < "$3" \
      | sed '/^SET transaction_timeout/d' \
      | docker exec -i "ilya-return-pg$1" psql -U postgres -d "$2" -X -q -v ON_ERROR_STOP=1 \
          --single-transaction >/dev/null
  fi
}

for v in 18 16; do
  stage "4.$v restaurar ilya e estoque no Postgres $v descartável"
  restore_into "$v" ilya_return "$DIR/ilya.dump"
  restore_into "$v" estoque_return "$DIR/estoque.dump"
  done_stage
done

stage "5. conferir contagens (banco em uso x restaurado) em 18 e 16"
fail=0
for v in 18 16; do
  for pair in "ilya-db:ilya:ilya_return" "estoque-db:estoque:estoque_return"; do
    IFS=: read -r svc live ret <<<"$pair"
    a=$(docker compose exec -T "$svc" psql -U postgres -d "$live" -X -At -c "$COUNT_SQL")
    b=$(docker exec "ilya-return-pg$v" psql -U postgres -d "$ret" -X -At -c "$COUNT_SQL")
    if [ "$a" = "$b" ]; then echo "   PG$v $ret: contagens iguais em $(echo "$a" | wc -l) tabelas"
    else echo "   PG$v $ret: DIFERENTE" >&2; diff <(echo "$a") <(echo "$b") >&2 || true; fail=1; fi
  done
done
done_stage

stage "6. religar a stack"
docker compose up -d --wait --wait-timeout 300 >/dev/null
done_stage

echo
echo "== Total do ensaio: $(( $(date +%s) - TOTAL_START ))s   (falhas: $fail)"
echo "   Criado e NÃO removido (remoção só com OK do responsável):"
echo "   containers ilya-return-pg18 e ilya-return-pg16, rede $NET, arquivos em $DIR"
exit $fail
