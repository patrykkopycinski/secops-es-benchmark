#!/usr/bin/env python3
"""
Append network-sensor telemetry (Zeek / Suricata / nginx) to each case export.

These indices are tagged with the SENSOR's host.name, not the victim's, so they are
filtered by the attack IP tuple instead of host.name (unlike export_dataset.py which does
endpoint by host). Run AFTER export_dataset.py; appends to each case's security.ndjson.

Env: ES_URL ES_USER ES_PASS BENCH_PSEUDO_SALT ; OUT=<dataset dir>
"""
import json, os, ssl, sys, urllib.request, collections, base64
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import pseudonymize
NET = "logs-zeek.*,logs-suricata.*,logs-nginx.*"
IPS = ["204.168.178.42", "135.181.180.110", "46.224.159.210"]
CASES = [
    ("case-01-recon", "2026-07-29T02:20:00Z", "2026-07-29T02:35:00Z"),
    ("case-02-collection-exfil", "2026-07-29T02:27:00Z", "2026-07-29T02:40:00Z"),
    ("case-03-web-exploit-revshell", "2026-07-29T02:44:00Z", "2026-07-29T03:00:00Z"),
    ("case-04-privesc", "2026-07-29T03:03:00Z", "2026-07-29T03:16:00Z"),
    ("case-05-lateral-movement", "2026-07-29T03:48:00Z", "2026-07-29T03:53:00Z"),
]
CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE

def es(method, path, body=None):
    url = os.environ["ES_URL"].rstrip("/") + path
    req = urllib.request.Request(url, data=(json.dumps(body).encode() if body is not None else None),
                                 method=method, headers={"Content-Type": "application/json"})
    tok = base64.b64encode(f'{os.environ["ES_USER"]}:{os.environ["ES_PASS"]}'.encode()).decode()
    req.add_header("Authorization", "Basic " + tok)
    return json.load(urllib.request.urlopen(req, context=CTX, timeout=60))

def run(name, start, end, outroot):
    outdir = os.path.join(outroot, name)
    pit = es("POST", f"/{NET}/_pit?keep_alive=2m").get("id")
    q = {"bool": {"filter": [{"range": {"@timestamp": {"gte": start, "lte": end}}}],
                  "minimum_should_match": 1,
                  "should": [{"terms": {"source.ip": IPS}}, {"terms": {"destination.ip": IPS}}]}}
    counts = collections.Counter(); total = 0; sa = None
    with open(os.path.join(outdir, "security.raw.ndjson"), "a") as raw, \
         open(os.path.join(outdir, "security.ndjson"), "a") as pse:
        while True:
            body = {"size": 1000, "track_total_hits": False,
                    "sort": [{"@timestamp": "asc"}, {"_shard_doc": "asc"}],
                    "pit": {"id": pit, "keep_alive": "2m"}, "query": q}
            if sa: body["search_after"] = sa
            res = es("POST", "/_search", body); hits = res.get("hits", {}).get("hits", [])
            if not hits: break
            for h in hits:
                src = h["_source"]; counts[src.get("data_stream", {}).get("dataset", "?")] += 1; total += 1
                line = json.dumps(src, ensure_ascii=False)
                raw.write(line + "\n"); pse.write(pseudonymize.scrub_json(line) + "\n")
            sa = hits[-1]["sort"]; pit = res.get("pit_id", pit)
    es("DELETE", "/_pit", {"id": pit})
    json.dump({"case": name, "network_by_ip": IPS, "window_utc": [start, end],
               "network_docs": total, "by_dataset": dict(counts)},
              open(os.path.join(outdir, "network_manifest.json"), "w"), indent=2)
    print(f"[net] {name}: +{total}  {dict(counts)}")

def main():
    for k in ("ES_URL", "ES_USER", "ES_PASS"):
        if not os.environ.get(k): sys.exit(f"set {k}")
    out = os.environ.get("OUT", os.path.abspath(os.path.join(HERE, "..", "..", "dataset")))
    for c in CASES: run(*c, out)
    print("NET_DONE_MARKER")

if __name__ == "__main__":
    main()
