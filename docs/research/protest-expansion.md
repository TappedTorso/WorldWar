# November 10 protest research edition

The current publication seed contains **453 source-reviewed observation records, of which 449 are eligible for occurrence counts, and 82 canonical campaign contexts**. Observations represent 119 reporting jurisdictions; occurrences and campaign contexts together represent 127. These are counts of documented records, not estimated national activity.

The finite September 1–November 10 source sweep covers 195 countries (193 UN members and two observer states) plus 12 additional reporting jurisdictions. Every one of the 207 has a country/date-specific query and a partial coverage assessment. Reporting codes do not imply a sovereignty judgment. This edition replaces the earlier 33-record sample and 42-jurisdiction discovery audit. It does not establish a global census, daily multilingual completeness or comparable country rates.

## Review and inclusion

The four regional packets add 93 observations in Africa/North America, 154 in Europe/South America, the individually validated Asia/Oceania additions recorded in the audit, and 40 in additional jurisdictions. Original organizer, union, authority and rights sources were preferred; substantive local and agency reporting also qualifies with attribution. Search titles and snippets were used for triage, never treated as sufficient completion evidence by themselves. Every published observation has an inclusion rationale and linked evidence.

Publication date, document date, source update, retrieval time and occurrence time remain separate. Month precision remains a month; uncertain intervals do not become daily actions. Unknown coordinates remain null. Aggregate or campaign reporting is not decomposed into invented local occurrences. Notices, cancelled actions, historical events republished in 2026, inaccessible evidence and unresolved date/geography/completion conflicts retain explicit dispositions.

All substantive review in these new packets is labeled research-agent source review. That label does not imply human editorial approval or independent corroboration. Source statements about demands, crowd size, institutional responsibility and effects retain their attribution and limits.

## Corrections and stable identities

The October 21 Galway strike record now has conflicting completion evidence. The University FAQ lists the strike; IFUT's October 16 notice suspends the national call; SIPTU's October 25 retrospective describes deferral. All three sources remain attached to the stable record `p-ie-galway-20261021`, which is excluded from totals pending local corroboration. National suspension does not prove that no Galway-specific action occurred. The separate October 14 strike and September 30 work-to-rule records are unchanged. `galway-completion-review.json` preserves the superseded earlier assessment with an explicit correction notice.

The South Africa asylum-processing campaign retains one canonical identity and a merged alias. New country coverage assessments reuse earlier country IDs; competing old assessments are explicit merged tombstones. No claim is silently repinned to a different source merely because two catalog entries share a URL.

## Reproducible audit and genuine limits

[`global-sweep-20261110.json`](global-sweep-20261110.json) contains exact query strings and available timing, all 207 current country assessments, source-review metadata, lead dispositions, packet hashes and identity merges. The same metadata-only audit is downloadable from Data & Methodology in the app. It excludes raw search responses, source full text, private paths and credentials. Missing initial response captures are disclosed; hashes and precise timestamps are not fabricated.

Source access restrictions, source/date conflicts, advance notices without completion evidence, weak relays and unresolved local units remain in the audit. Those are real coverage gaps. Missing observations never establish zero activity. The original 82 conflict actors and 75 relationships remain inherited and unverified; the expanded protest review does not reverify them. Election reporting retains 11 unofficial tally observations and 459 unassessed registry records, without invented winners.

Rebuild with `npm run build` using the documented Python environment, then run `npm run check:public` and `python scripts/validate_research_edition.py`. The latter checks the saved evidence contract, seed/public parity, counting/date semantics, source pins, stable identities and operative geometry. Passing software checks is not a factual-completeness certificate.
