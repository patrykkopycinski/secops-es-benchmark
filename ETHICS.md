# Ethics, Legal & Responsible-Use Statement

## Authorization & ownership
All systems used to generate this dataset — the attacker/C2 host, both victim hosts, and
the Elasticsearch cluster — are **owned and operated by the dataset authors**. All attack
activity was **self-authorized red-teaming on our own infrastructure**. No third-party
systems were scanned, accessed, or attacked. No unauthorized access occurred.

## No third-party or personal data
- The environment is a controlled lab/production-of-our-own; it does not contain customer
  PII by design. Any staged "sensitive" data in the attack scenarios is **synthetic decoy**
  (e.g., `DECOY_AKIA_BENCH`, fabricated CSV rows).
- Secrets and business/PII are **removed** before release (see `DATASHEET.md` and
  `benchmark/lib/pseudonymize.py`): a DB password, OS password hashes, private keys, API
  tokens, email addresses, and business identifiers do not appear in the distributed files
  (verified 0 residual). Network identifiers (IPs, hostnames) appear as captured so the
  data stays investigable; third-party addresses in the background noise are public-actor
  network metadata (scanners, public services), retained as-is.

## Safety of the artifacts
- The dataset is **log data only**. Strings like `/tmp/.sysupdate`, `/tmp/.shell.php`, or
  reverse-shell command lines are **inert text in event records** — no malware binaries,
  no live C2, no exploit payloads are distributed.
- The included attack scripts (`corpus/scenarios/*.sh`) perform **non-destructive**,
  well-known ATT&CK techniques for detection research. They require a Sliver C2 and a
  consenting lab to run and are provided for reproducibility, not for use against systems
  you do not own.

## Intended use & prohibited use
- **Intended:** benchmarking SOC/AI investigation agents, detection engineering, teaching,
  and correlation research.
- **Prohibited:** using the scenarios or any derived tooling against systems you are not
  authorized to test; attempting to re-identify the source environment.

## Licensing
Data under **CC-BY-4.0** (`LICENSE-DATA`); code/scripts under **Apache-2.0**
(`LICENSE-CODE`). Attribution appreciated per the dataset citation in `README.md`.

## Contact / disclosure
Issues, re-identification concerns, or takedown requests: open an issue at
https://github.com/TocharianOU/secops-es-benchmark/issues
