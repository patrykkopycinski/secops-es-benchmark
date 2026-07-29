#!/usr/bin/env bash
# Deploy the read-only demo (ES + Kibana + ingress) WITHOUT committing any password.
# Passwords come from lab/.env (gitignored). Usage:
#   cp lab/.env.example lab/.env && edit lab/.env
#   ./lab/deploy.sh
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
[ -f "$HERE/.env" ] || { echo "create $HERE/.env from .env.example first"; exit 1; }
set -a; . "$HERE/.env"; set +a
: "${ELASTIC_PASSWORD:?}"; : "${KIBANA_SYSTEM_PASSWORD:?}"; : "${BENCHMARK_RO_PASSWORD:?}"

kubectl apply -f "$HERE/es-bench.yaml"          # namespace + ES (no Secret inside)

# create/replace the credentials Secret from env (never stored in git)
kubectl -n es-bench create secret generic es-bench-credentials \
  --from-literal=ELASTIC_PASSWORD="$ELASTIC_PASSWORD" \
  --from-literal=KIBANA_SYSTEM_PASSWORD="$KIBANA_SYSTEM_PASSWORD" \
  --from-literal=BENCHMARK_RO_PASSWORD="$BENCHMARK_RO_PASSWORD" \
  --dry-run=client -o yaml | kubectl apply -f -

# restart ES pod so it bootstraps with the Secret, wait, then provision + Kibana/ingress
kubectl -n es-bench delete pod es-bench-0 --ignore-not-found
echo "[*] waiting for ES..."; kubectl -n es-bench rollout status statefulset/es-bench --timeout=300s || true
echo "[*] Now provision users + load data (see lab/README.md), then:"
echo "    kubectl apply -f $HERE/es-bench-public.yaml"
