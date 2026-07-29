#!/usr/bin/env bash
# Export raw ES evidence for one case time-window to NDJSON, then pseudonymize.
#
# Data lives in the LIVE cluster; this snapshots the docs behind a case so the
# corpus is portable / shareable (after pseudonymization).
#
# Setup (do NOT commit the password):
#   export ES_URL="https://your-es-host:9200"
#   export ES_USER="elastic"
#   export ES_PASS="<the elastic password>"     # from Kibana / your ES keystore
#   export BENCH_PSEUDO_SALT="<stable secret>"
#
# Usage:
#   ./export_case.sh <out_dir> <host.name> <start_utc> <end_utc> [index_pattern]
# Example (case-01):
#   ./export_case.sh ../../corpus/cases/case-01-recon/raw ubuntu-2404-noble-amd64-base \
#       2026-07-29T02:20:00Z 2026-07-29T02:35:00Z
set -euo pipefail

OUT="${1:?out_dir}"; HOST="${2:?host.name}"; START="${3:?start_utc}"; END="${4:?end_utc}"
INDEX="${5:-logs-endpoint.events.*,logs-zeek.*,logs-suricata.*,logs-nginx.*,.alerts-security.alerts-*}"
: "${ES_URL:?set ES_URL}"; : "${ES_USER:?set ES_USER}"; : "${ES_PASS:?set ES_PASS}"
HERE="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$OUT"

query() {
  cat <<JSON
{ "size": 10000,
  "sort": [{"@timestamp": "asc"}],
  "query": { "bool": { "filter": [
    {"range": {"@timestamp": {"gte": "$START", "lte": "$END"}}},
    {"term": {"host.name": "$HOST"}}
  ]}}}
JSON
}

RAW="$OUT/evidence.raw.ndjson"
echo "[*] exporting $INDEX  host=$HOST  $START..$END"
curl -sk -u "$ES_USER:$ES_PASS" -H 'Content-Type: application/json' \
  "$ES_URL/$INDEX/_search" -d "$(query)" \
| python3 -c 'import sys,json; [print(json.dumps(h["_source"])) for h in json.load(sys.stdin).get("hits",{}).get("hits",[])]' \
> "$RAW"
echo "[*] $(wc -l < "$RAW") docs -> $RAW"

# pseudonymize (deterministic; preserves correlatability)
python3 "$HERE/pseudonymize.py" < "$RAW" > "$OUT/evidence.pseudo.ndjson"
echo "[*] pseudonymized -> $OUT/evidence.pseudo.ndjson"
echo "[!] keep evidence.raw.ndjson private; distribute only *.pseudo.ndjson"
