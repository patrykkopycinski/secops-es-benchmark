#!/usr/bin/env python3
"""
Load the pseudonymized benchmark dataset into an Elasticsearch you control.

Preserves the original query surface: docs are routed to `{type}-{dataset}-bench`
(e.g. logs-endpoint.events.process-bench, logs-zeek.connection-bench), so the benchmark
tasks' index patterns (logs-endpoint.events.*, logs-zeek.*, logs-suricata.*, logs-nginx.*)
match unchanged. Security detection alerts (no data_stream) go to `benchmark-alerts-security`.

Env: ES_URL ES_USER ES_PASS    (e.g. http://localhost:9200 / elastic / <pw>)
Usage: python3 load.py [dataset_dir]     # default: ../  (the dataset/ folder)
"""
import gzip, json, os, ssl, sys, glob, base64, urllib.request, collections
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.abspath(os.path.join(HERE, ".."))
CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE

def es(method, path, body=None, ndjson=False):
    url = os.environ["ES_URL"].rstrip("/") + path
    if ndjson:
        data = body.encode(); ctype = "application/x-ndjson"
    else:
        data = json.dumps(body).encode() if body is not None else None; ctype = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": ctype})
    tok = base64.b64encode(f'{os.environ["ES_USER"]}:{os.environ["ES_PASS"]}'.encode()).decode()
    req.add_header("Authorization", "Basic " + tok)
    with urllib.request.urlopen(req, context=CTX, timeout=120) as r:
        return json.load(r)

_BULK_ERR = {"n": 0, "sample": None}

def bulk(payload):
    res = es("POST", "/_bulk", payload, ndjson=True)
    if res.get("errors"):
        for it in res.get("items", []):
            err = (it.get("index") or {}).get("error")
            if err:
                _BULK_ERR["n"] += 1
                if _BULK_ERR["sample"] is None:
                    _BULK_ERR["sample"] = err

def target_index(src):
    # detection-engine alerts first — they inherit a data_stream from the source event
    # but belong in their own index (mirrors .alerts-security). Fields may be stored as
    # dotted keys ("kibana.alert.rule.name", "event.kind") OR nested objects.
    is_alert = (
        src.get("event.kind") == "signal"
        or (isinstance(src.get("event"), dict) and src["event"].get("kind") == "signal")
        or any(k.startswith("kibana.alert") for k in src)
        or (isinstance(src.get("kibana"), dict) and "alert" in src["kibana"])
    )
    if is_alert:
        return "benchmark-alerts-security"
    ds = src.get("data_stream") or {}
    t, d = ds.get("type"), ds.get("dataset")
    if t and d:
        return f"{t}-{d}-bench"
    return "benchmark-misc"

def main():
    for k in ("ES_URL", "ES_USER", "ES_PASS"):
        if not os.environ.get(k): sys.exit(f"set {k}")
    # templates
    es("PUT", "/_component_template/benchmark-secops-mappings", json.load(open(f"{HERE}/component-template.json")))
    es("PUT", "/_index_template/benchmark-secops", json.load(open(f"{HERE}/index-template.json")))
    print("[*] templates installed")
    counts = collections.Counter(); total = 0
    for gzf in sorted(glob.glob(os.path.join(DATA, "*", "security.ndjson.gz"))):
        case = os.path.basename(os.path.dirname(gzf)); buf = []; n = 0
        def flush():
            nonlocal buf
            if not buf: return
            bulk("".join(buf)); buf = []
        with gzip.open(gzf, "rt") as f:
            for line in f:
                line = line.strip()
                if not line: continue
                src = json.loads(line); idx = target_index(src)
                counts[idx.split("-bench")[0]] += 1; n += 1; total += 1
                buf.append(json.dumps({"index": {"_index": idx}}) + "\n" + line + "\n")
                if len(buf) >= 1000: flush()
            flush()
        print(f"[*] {case}: {n} docs")
    es("POST", "/_refresh")
    print(f"[*] DONE {total} docs. top indices:")
    for k, v in counts.most_common(12): print(f"    {k}-bench : {v}")
    if _BULK_ERR["n"]:
        print(f"[!] {_BULK_ERR['n']} docs rejected by _bulk. first error: {_BULK_ERR['sample']}")
    else:
        print("[*] no _bulk errors")

if __name__ == "__main__":
    main()
