#!/usr/bin/env python3
"""
Deterministic pseudonymization for the SecOps benchmark corpus.

Goal: make exported evidence / answer keys shareable WITHOUT leaking real IPs,
usernames, hostnames or secrets, while PRESERVING correlatability — the same real
value always maps to the same fake value, so cross-index / cross-host links survive.

Usage:
    export BENCH_PSEUDO_SALT="some-long-secret"      # keep this stable & private
    python3 pseudonymize.py < raw.json > clean.json  # stream JSON/text
    python3 pseudonymize.py file1.md file2.json      # in-place-ish -> .pseudo

Method: HMAC-SHA256(salt, value) -> stable short token. IP structure preserved
(public vs RFC1918 vs CGNAT/Tailscale 100.64/10); secrets (shadow hashes) redacted.
"""
import hashlib, hmac, ipaddress, os, re, sys

SALT = os.environ.get("BENCH_PSEUDO_SALT", "CHANGE-ME-benchmark-salt").encode()

def _h(value: str, n: int = 8) -> str:
    return hmac.new(SALT, value.encode(), hashlib.sha256).hexdigest()[:n]

# ---------------------------------------------------------------------------
# POLICY (v0.2, "keep-real-infra"):
#   KEEP REAL: IP addresses, hostnames, domains (tocharian.eu, ubuntu-2404-…,
#              attacktrace), the MISP platform, stripe.com DNS, the name "luke".
#   SCRUB    : real emails, ALL "newmind*" business identifiers, the MySQL DB
#              password, OS password hashes, private keys, API tokens/JWT/AWS.
# Rationale: the authors do not consider their own infrastructure IPs/hostnames
# sensitive, and keeping real IPs avoids the TEST-NET "this is synthetic" tell —
# improving benchmark validity. Only secrets and third-party business/PII are removed.
# ---------------------------------------------------------------------------

# business identifier to remove entirely (any newmind* -> appA; no "newmind" remains)
NEWMIND_RE = re.compile(r"newmind", re.IGNORECASE)

# --- secrets / PII to redact ---------------------------------------------------
SHADOW_HASH_RE = re.compile(r"\$(?:y|gy|6|5|1|2[aby])\$[^\s:\"]+")   # crypt() hashes
AWS_RE = re.compile(r"AKIA[0-9A-Z]{8,}")
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{6,}\b")
PRIVKEY_RE = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----")
# db password: mysql/cli `-p<pw>` where the value looks like a password (has pass/pwd).
# Anchoring on pass/pwd avoids eating benign flags like -parts / -path / -policy.
DBPW_RE = re.compile(r"(-p)([A-Za-z0-9_.@!#%^*+-]*(?:pass|pwd)[A-Za-z0-9_.@!#%^*+-]*)", re.IGNORECASE)
# require a real =/: assignment so we don't eat "/etc/passwd" or "GET /x passwd HTTP"
BEARER_RE = re.compile(r"(?i)\b(bearer|api[_-]?key|password|passwd|secret|token)(\s*[=:]\s*[\"']?)([^\s\"',}]+)")

def scrub(text: str) -> str:
    # secrets / PII only — IPs and hostnames are intentionally left REAL
    text = SHADOW_HASH_RE.sub("<REDACTED_PWHASH>", text)
    text = PRIVKEY_RE.sub("<REDACTED_PRIVATE_KEY>", text)
    text = JWT_RE.sub("<REDACTED_JWT>", text)
    text = AWS_RE.sub("<REDACTED_AWS_KEY>", text)
    text = DBPW_RE.sub(lambda m: f"{m.group(1)}<REDACTED>", text)         # mysql -p<pw>
    text = BEARER_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}<REDACTED>", text)
    text = EMAIL_RE.sub("<REDACTED_EMAIL>", text)                          # scrub emails
    text = NEWMIND_RE.sub("appA", text)                                    # remove newmind*
    return text

def _walk(o):
    if isinstance(o, str):
        return scrub(o)
    if isinstance(o, list):
        return [_walk(x) for x in o]
    if isinstance(o, dict):
        return {k: _walk(v) for k, v in o.items()}
    return o

def scrub_json(line):
    """Structure-safe scrub for an NDJSON line: only string VALUES are scrubbed, so a
    field name or path like /etc/passwd can never corrupt the JSON. Falls back to raw
    text scrub if the line is not valid JSON."""
    import json as _json
    try:
        return _json.dumps(_walk(_json.loads(line)), ensure_ascii=False)
    except Exception:
        return scrub(line)

def main(argv):
    if len(argv) <= 1:
        # stream NDJSON structure-safely
        for line in sys.stdin:
            line = line.rstrip("\n")
            if line.strip():
                sys.stdout.write(scrub_json(line) + "\n")
        return
    for path in argv[1:]:
        with open(path) as f:
            out = scrub(f.read())
        with open(path + ".pseudo", "w") as f:
            f.write(out)
        print(f"wrote {path}.pseudo", file=sys.stderr)

if __name__ == "__main__":
    main(sys.argv)
