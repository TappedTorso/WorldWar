# Backend acceptance evidence

`restore-proof.json` is a real private-store backup/restore verification completed November 10, 2026 at 06:47:33 UTC. It restored into a fresh SQLite database and compared the canonical content of **every table** and the complete public export snapshot. Both comparisons passed. Typed table counts are per immutable revision, so 164 actor rows represent the 82 actor identities with separate create/publication revisions.

The fixed proof dataset included:

- All 82 original conflict actors and 75 relationships, exact original payloads and metadata, geographic identity crosswalks, and inherited/unverified evidence labels.
- The v4 reviewed packet: 19 protest occurrences, 5 campaigns, 470 contest registry/result records, 15 reviewed conflict developments, 17 election actions, 6 political-context records, 64 coverage entries, and linked source metadata.
- The official-source unofficial result override, preserving dated prior revisions.
- All 15,557 canonical discovery article candidates and their source metadata, provider-seen/retrieval/repository provenance, immutable draft/publication revisions, evidence and actor context links.
- Two public original collection-run reports and the private archive reconstruction job.

There were 31,923 stable identities, 63,852 immutable revisions and 32,351 evidence links. Source/campaign/actor/domain projection tables retain each revision independently. No source full text or environment editor token was included. Private unpublished create revisions and reasons were included in the **private** backup; separate test fixtures also prove preservation of a currently unpublished correction/draft.

Input import-batch digests (canonical structured JSON, not raw file-byte hashes):

| Input | SHA-256 |
| --- | --- |
| Original legacy map | `491753de203a1e3f55fe4dc6d75aad9452700c32198c490a4ef0338bc5e910ab` |
| Frozen v4 reviewed packet | `2fffec4445a6c184afdbee850978bd5e5efd95b497ae8400390684f47e36c77f` |
| Official-source observations | `e144e703bdc4141b119a59822d296bbfe8c123da5ee271a2caaccbe15b50a657` |

The coordinator's later House-geometry audit and subsequent research additions were outside this fixed proof source. They use the same validated import/service path; this report does not claim their later dataset was the one restored.

The full roundtrip used approximately 534 MB of temporary disk (191 MB private backup, 152 MB restored database, 191 MB second private backup), which the verification removed after comparison. The resource-constrained desktop spent about 14 minutes wall time under severe memory compression/swap, while the Python process used about a minute of CPU. Subsequent memory changes stream canonical hashing, bound restore inserts to 500 rows, and compare snapshot digests without retaining two full snapshot dictionaries. A targeted real roundtrip test passed after those changes, and a canonical-hash equivalence check confirmed the streaming digest matches the prior implementation.

The full 32-test suite passed before the final campaign-retraction regression was added. The additional regression, immutable-projection/archive/restore checks and updated recovery check passed individually. The suite covers authentication and disabled editor behavior; private publication separation; actual concurrent compare-and-swap; forbidden ORM/direct-SQL history rewrites; malformed/source URL and reserved-provenance rejection; every original legacy payload; seed atomicity/cyclic membership; canonical discovery deduplication and failed refresh retention; source date precision; bounded snapshot versus full API archive; export parity and formula escaping; retraction/merge histories; scorecard corrections, uncertain ranges, coverage gating and campaign retraction; bounded official-source result observations; private protest source candidates; and backup corruption/nonempty-target protection.

Local host validation used Python 3.14 and SQLite. Exact runtime/test versions are pinned. Docker was unavailable on this host, so the container files were reviewed for build paths, nonroot execution, secret injection, service names, persistent storage and reverse-proxy/health-check consistency without claiming a local Docker run. The explicit live PostgreSQL proof script is `tests/postgres_smoke.py --disposable-test-database`; its execution belongs to the coordinator's disposable PostgreSQL CI service, rather than an invented local PostgreSQL success.
