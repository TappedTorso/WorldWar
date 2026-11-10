# Additive chronology handoff v4

`additions-v4.json` is the integration input: **22 new sources, 15 conflict developments, 15 election actions, and two bounded coverage records**. Merge by stable ID into the current parent snapshot. Do not replace the parent's newer contest/result data with a stale full snapshot. `../snapshot-seeds-v4.json` is a convenience merge against the preserved v3 research packet, containing 54 sources, 15 developments and 17 election actions in total.

All new domain records have `evidence_status: reviewed`, `publication_status: published`, a real review timestamp, identified supporting sources and a source locator. All conflict records use `development_type: reported_development`. Every linked actor ID exists in the legacy 82-actor catalog. All new occurrence/action dates are in 2026 and no later than November 10. Published domain records contain original brief summaries and links, not source text or media.

## What the new conflict chronology establishes

The 15 records cover specific reported attacks and infrastructure effects in Ukraine; Gaza rain disruption and meal-production recovery; a dated Hebron operation end, Khirbet Suruj displacement, fire near UN operations, and an Egypt-origin shipment suspension notice; Myanmar health-service delivery over a stated quarter; a dated UNHCR/IOM Sudan warning; a Haiti Security Council resolution vote; completion of UNICEF's Lebanon visit; September returnee registrations in Chad; and an August attack on a WFP convoy in Dilling.

The recorded events and source dates are deliberately distinct:

| Evidence | Event/valid period used | Document/publication date |
|---|---|---|
| [UN DPPA Ukraine address](https://www.unmissions.org/en/dppa/speeches-and-statements/remarks-by-director-for-europe-and-central-asia-division-to-the) | November 2 school/shelter attack; November 3 hospital strike; October 30–November 2 energy impacts | November 9 address |
| [OCHA heavy-rain report](https://www.ochaopt.org/content/humanitarian-situation-report-heavy-rains-gaza-strip-8-november-2026) | Rain November 6–8; kitchens disrupted November 7 and production restored November 8 | Report label November 8; website publication November 9 |
| [OCHA November 5 report](https://www.ochaopt.org/content/humanitarian-situation-report-5-november-2026) | October 29, November 1, November 2 and November 3 explicitly dated incidents | Report label November 5; website publication November 6 |
| [Myanmar Health Cluster bulletin](https://myanmar.un.org/sites/default/files/2026-11/Myanmar%20Health%20Cluster%20Bulletin_Sep-Oct2026.pdf) | July 1–September 30 health-service delivery | Document October 30; precise hosting publication date unknown |
| [IOM Chad update](https://dtm.iom.int/reports/chad-sudan-crisis-response-returnee-situation-update-eastern-region-round-69-september-2026) | September 1–30 registrations | Exact publication date unknown |
| [EEAS convoy statement](https://www.eeas.europa.eu/delegations/sudan/statement-attack-against-world-food-programme-convoy_en) | August 30 incident | September 4 statement |

Numbers remain attributed to the source. An actor link provides topical/geographic context; it is not a perpetrator finding. Egypt is shipment-origin context, for example. No conflict relationship, inherited confidence value or legacy verification date is changed. The unrecovered user report titled “Global Conflict Systems, Organized Violence, and Conflict-Connected Exposure” remains an unresolved provenance gap; these sources are not replacements for its old claims.

## What the election chronology establishes

The 15 new actions retain the requested focus on federal administration/agency action, congressional map changes and court responses:

- March 30 FCC Media Bureau advertising-rate notice, described in the Court's later opinion.
- March 31 presidential signature of EO 14399, with April 3 Federal Register publication.
- May 4 Florida gubernatorial approval of congressional-map legislation.
- June 2 USPS proposed rule; August 26 final-rule publication; October 20 USPS statement of nonimplementation/nonenforcement for the 2026 General Election.
- August 24 Supreme Court stay concerning the election executive order.
- September 25 Missouri map order, October 14 FCC timing order, and October 22 New Hampshire injunction stay.
- October 15 DOJ California lawsuit, October 26 dismissal of its initial Ninth Circuit appeal, October 22 DOJ Alaska suit, November 1 Alaska dismissal without prejudice, and November 2 DOJ enforcement announcement.

The [EO text](https://www.govinfo.gov/content/pkg/DCPD-202600219/html/DCPD-202600219.htm) distinguishes presidential directives from later agency implementation. The [USPS final rule](https://www.govinfo.gov/content/pkg/FR-2026-08-26/html/2026-17238.htm) states an August 21 effective date despite August 26 publication. The later [October 20 USPS release](https://about.usps.com/newsroom/local-releases/co/2026/1020-usps-says-its-business-as-usual-for-the-2026-election.htm) explicitly says the rule was not being implemented or enforced for the 2026 General Election. Neither promulgation nor an interlocutory stay is treated as proof that a policy was implemented at the polls.

The [Alaska dismissal PDF](https://www.govinfo.gov/content/pkg/USCOURTS-akd-3_26-cv-00376/pdf/USCOURTS-akd-3_26-cv-00376-0.pdf) expressly dates the original suit **October 22**, not October 23; amendment October 29; and dismissal November 1. Its allegations-accepted-for-dismissal background does not become trial findings. The [Ninth Circuit opening order](https://www.govinfo.gov/content/pkg/USCOURTS-ca9-26-7070/pdf/USCOURTS-ca9-26-7070-0.pdf) is October 26 and dismisses the initial California appeal for lack of jurisdiction; the 91-page PDF compilation contains other material that is not silently merged into that holding.

`claim_status: court_finding` identifies the narrow operative procedural disposition only. DOJ noncitizenship and voter-confusion allegations remain attributed; neither an allegation nor a criminal charge establishes guilt. All `effect_claim`, `effect_evidence`, `intent_claim` and `intent_evidence` values remain null. The records do not claim a quantified vote effect, partisan intent, misconduct finding, completed recount/certification or exhausted appeal process. `status_as_of` is the historical action date, rather than an assertion that an interlocutory order remains in force today without checking the docket.

## Verification and source access

`validation-v4.json` passes stable-ID uniqueness, source references, legacy-actor ID validation, date cutoff, reviewed-development type and no inferred election effects. `source-validation-v4.json` supplies each source's exact URL, scope/locator, publication/document date, retrieval precision, HTTP proof and supported record IDs. `http-ledger.json` preserves failed and successful acquisition attempts, including exact UTC timestamps and content hashes when usable.

Most documents were reviewed in their full primary text. OCHA, UN DPPA, the Myanmar bulletin, UNICEF and the legal PDFs/HTML were independently fetched and inspected. UNHCR/IOM's Sudan release, IOM's Chad report, EEAS's convoy statement and the UN Journal Haiti meeting were reviewed through substantive indexed extracts from their primary publishers; direct requests returned 403/429 or an unusable JavaScript shell. Those records make only the narrow statements explicitly available in the extract, and this access limitation remains in each source row. The DOJ California press release was fully readable through the web tool, while a separate HTTP request returned a 200 challenge page with no usable text; that body hash is not presented as evidence.

No ASR-only assertion was promoted: the newer `transcripts.un.org` pages explicitly say their automatic transcripts are not official records. Their unconfirmed location/casualty spellings were not used. Similarly, search leads about late California dismissal, additional sanctions, Yemen custody and Cyprus outcomes were not turned into assertions without sufficient bounded primary evidence.

The packet supports an expanded dated chronology, not complete history for every conflict or a comprehensive national election litigation docket. No paid services, accounts, remote publication, external messages or original-checkout edits were made.
