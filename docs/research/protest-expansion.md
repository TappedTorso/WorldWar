The integrated publication in `data/publication/seed.json` includes the v5 expansion: **12 source-dated occurrence additions and three source-context additions touching 12 countries, of which 11 are newly represented relative to v3**, supported by 16 primary sources. The South Africa campaign addition has been consolidated with an existing campaign while preserving its former ID as a merged record. The countries are Argentina, Austria, Netherlands, Ireland, Philippines, Mexico, South Africa, Canada, Brazil, Australia, Iran and the United States. The final collection has 31 occurrences across 20 countries, plus seven canonical campaign records and one merged alias. Occurrences and campaigns together represent 22 countries; Australia and the United States enter through campaign context only in this batch. This remains a bounded collection, not a worldwide census.

Integration retained election and boundary updates. `za-campaign-reconciliation.json` records the campaign deduplication, evidence, preserved source dates and explicit publication action. Original source-validation results remain dated records of their respective research batches.

| Country | Reviewed addition | Event date or precision |
| --- | --- | --- |
| Argentina | University funding march at Plaza del Congreso, Buenos Aires | October 15; union retrospectives |
| Netherlands | Amsterdam climate march | September 12; organizer report |
| Austria | Amnesty banner protest at football match, Linz | September 24; organizer caption and completed-action account |
| Ireland | University of Galway staff stoppage and strike | October 5 and 14; university operational record |
| Philippines | Farmers’ protest outside agrarian reform department, Quezon City | October 19; rights commission response/investigation |
| Mexico | Students and civic groups’ Tlatelolco remembrance march | October 2; rights commission monitoring |
| South Africa | George demonstration against gender-based violence and femicide | September 18; municipal participant report |
| Canada | Active Dynamics and Autobus Venise strike onsets | October 19 and 22; union reports |
| Brazil | Grito dos Excluídos gathering at INPA, Manaus | September 7; local Indigenous rights organization report |
| Iran | Sanandaj merchants’ commemorative strike | September 16; local rights monitor |
| South Africa | Protests concerning resumed asylum processing | Campaign context; exact start/end unknown |
| Australia | New South Wales community-preschool funding campaign | Completed rallies confirmed by November 5; exact dates unknown |
| United States | No Kings: Vote Early national day | October 17 coordinated campaign context; individual local completions unassessed |

`protest-coverage-audit.json` logs bounded discovery/review activity for 42 jurisdictions, the target September 1–November 10 event window, domain restrictions, normalized query descriptions, decisions and gaps. The query descriptions are not claimed to be a complete verbatim engine log. The exact reviewed source URLs and actual capture provenance are in `source-validation-v5.json` and `http-ledger-v5.json`. Forty-two searched jurisdictions do not mean forty-two countries have verified event coverage. The public packet marks twelve countries touched by the expansion partial; eleven are newly represented overall, retains existing partial New Zealand coverage, marks the other twenty-nine country histories not assessed, and retains a partial worldwide coverage record.

The search spans North and South America, Central America, the Caribbean, Northern/Western/Eastern/Southern Africa, Europe, the Caucasus, Central/Southern/Eastern/Southeast/Western Asia, and Oceania. Central Africa, most Pacific island states, much of Central Asia and many other countries have not received individual primary-source assessment. Searches were selective and not a daily multilingual crawl. Unobserved places or dates never mean zero events.

`source-validation-v5.json` maps each published record to its exact supporting primary source and evidence locator. Fifteen of the sixteen primary sources have independently captured bodies and hashes. The George Municipality source was fully read through the web tool, including the dated event account and publication footer, but independent HTTP returned 404; that limitation is explicit and no hash is fabricated. Raw source files and parsed text under `raw/` are internal review materials and must not be copied into public exports.

Several exclusions materially affect reliability:

- The October 2026 Kenya rights report documents 2023–2025 protest events. Its publication date does not create a new 2026 protest.
- Nepal’s September uprising sources mainly concern 2025. Contemporary anniversary material needs its own review.
- Nova Scotia’s proposed November 2 strike was averted according to the official government update. Union notices and authorization votes are not completed strikes.
- The Australian November 5 union retrospective confirms earlier rallies but does not date them. Advance notices remain separate; November 6/13 events are not presumed completed.
- A secondary legal article’s purported SAPS protest URL returned an unrelated illegal-mining statement. It was rejected despite HTTP 200. A separate verified police statement republished by eThekwini supports recent campaign context only; its arrest timing is not used to date protests.
- The United States national mobilization includes voter-participation activity. It is campaign context rather than a single protest occurrence, and organizer turnout, platform-interference and electoral-effect claims are not imported.

Unreviewed leads and exclusions remain in the private research workspace and are not included in this repository or eligible for counts. `validation-v5.json` verifies stable-ID uniqueness, lack of collisions with v3, source references, event dates within the requested window, no completed future actions and unknown campaign dates retained as null. Strike records count their documented onset once, not every day of an ongoing dispute. City coordinates remain null because source-linked geocoding was not part of this batch.

Rebuild the integrated public edition with `npm run build` after installing the documented dependencies. This consumes the versioned publication seed, official result observations and discovery archive; it does not retrieve or re-review source bodies. Historical collection and assembly scripts, raw captures and private candidate notes remain in the research workspace. Public ledgers retain source URLs, dates, retrieval outcomes, hashes and factual scope; private capture paths are omitted. A new HTTP retrieval is not itself a new substantive source review.
