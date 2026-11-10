# U.S. midterms addendum to the unified project proposal

Prepared October 26, 2026. Official-source research checked at approximately 16:47 UTC / 12:47 p.m. America/New_York. This adds a third subject area to [the October 25 unified proposal](./2026-10-25-proposal.md); it preserves that report and its dated repository/live-site findings. It is conceptual reassessment for discussion, not execution planning or implementation.

**Recommendation: add U.S. Elections to the same application, using the same map → chronological developments → evidence/detail pattern as Conflicts and Protests. Begin with the 2026 midterms, a clear House/Senate geographic baseline, an evolving race/results map, and a focused chronology of documented administration/Republican actions affecting the election. Keep the initial experience straightforward: sourced updates with explicit status/freshness, without assuming a particular live vote-counting service, forecasts, or a separate election platform.**

The user’s investigative interest is legitimate and should remain visible. A collection can focus on the current administration and Republican actors without presuming that every action is misconduct. The product should show what was done or proposed, by whom, under what authority, where it applies, what changed procedurally, the stated rationale, and what evidence supports claimed effects. Intent, wrongdoing, coordination, and consequences require their own evidence and attribution. Equivalent claims should receive the same evidentiary standard regardless of actor; this does not require artificial equal numbers of stories about each party.

## What changes in the unified recommendation

The application becomes **Overview · Conflicts · Protests · U.S. Elections · Data & Methodology**, with shared search and a consistent exploration/reading experience. Those are provisional labels. There is still one product, one research foundation, and one maintenance path. Election activity must not be forced into protest occurrences or conflict relationships, and no combined elections/conflict/protest score is proposed.

The third area reinforces the need for stable IDs, source provenance, corrections, meaningful dates, and reusable storage. It does **not** justify microservices or three frontend applications. The modular monolith, PostgreSQL, background jobs, and protected editorial workspace remain appropriate planning defaults.

Two refinements are warranted. First, geographic data now needs explicit jurisdiction and district-boundary versions; the existing country map cannot provide that by relabeling polygons. PostgreSQL with PostGIS is a stronger planning candidate for this shared geographic requirement, while the exact serving/rendering approach remains a later decision. Second, common chronology should be a reusable interface over typed domain records, not a single generic “event” table that erases whether an entry is a battle development, demonstration, filed lawsuit, rule, or election result update.

The user’s clarification favors shared patterns and restraint. I therefore recommend a bounded election module, not the broader election-data platform that all available sources could theoretically support. No polling model, predictive odds, voter database, precinct explorer, donor network, campaign messaging, contact tool, or personalized political targeting is implied.

## The straightforward election experience

The default election screen should combine a U.S. map, a date range, and chronological update cards. Selecting a state or district filters relevant developments; selecting a development highlights its documented geographic scope. A national action can be labeled nationwide without placing a misleading event marker in Washington. Users should be able to keep national developments visible while examining a local race.

**The map can naturally look like a live-results map and update as the election develops. There is no reason to prohibit that appearance or impose a special visual separation.** Accuracy comes from explicitly labeling what each layer/color means, its source, status, and freshness. Results are a natural part of the concept; the unresolved decision is the acquisition/refresh commitment behind them, not whether the design is allowed to resemble a results dashboard.

Provide two simple views of the same workspace:

- **Election map:** selected race layer, basic contest information, relevant milestones, status and source date, with an official-source link. A detail preview can show candidates where the ballot list is verified, district vintage, election stage, and the relevant update history.
- **Election actions:** the focused accountability chronology, filterable by actor, action type, jurisdiction, and procedural status. The map shows where an action applies or is alleged to matter, explicitly distinguishing those two meanings.

These can be tabs or a view toggle; they need not become separate products. Reuse the existing proposal’s selected-record preview, stable detail page, evidence expansion, chronology, retained filters, mobile map/list/detail modes, and loading/empty/stale/coverage states.

Three principal user journeys are enough to define the addition:

1. **What changed here?** Select a state/district, see which included contests are occurring, and read dated election developments with source/status labels.
2. **What did this actor do, and where does it stand?** Open a documented action, follow proposal/adoption/challenge/order/implementation developments, and inspect the actual document or attributed reporting.
3. **What is the evidence for its electoral effect?** Separate the action’s documented scope and stated rationale from an allegation, analysis, measured outcome, or court finding. Follow supporting and contradictory evidence without turning an inferred effect into an established fact.

A map color must name its meaning. Party affiliation, incumbent party, latest reported leader, projected winner, and certified winner are different attributes. “No Senate contest this cycle,” “not yet reported,” “not assessed,” and “unavailable” are different states. Avoid coloring every state as if it has the same set of races. A small state/seat list alongside the geography prevents land area from appearing to represent electoral importance.

## Recommended initial scope and meaningful alternatives

The **working cycle is the 2026 U.S. midterms**, pending any correction from the user. The FEC currently identifies **November 3, 2026** as the next regularly scheduled federal general election. On October 26 that is eight days away; this is a timing constraint for eventual prioritization, not a promise that the full three-domain application can responsibly launch by then. [FEC election information](https://www.fec.gov/introduction-campaign-finance/election-results-and-voting-information/).

| Scope | Product value | Tradeoff |
|---|---|---|
| State overview with Senate contests | Smallest coherent initial geography; useful for national actions and statewide context | Omits the House as a central midterm subject; district/redistricting stories have less useful context |
| **House districts plus Senate contests — recommended** | A recognizable federal-midterm baseline, with state overview and district drilldown | Requires verified 2026 district plans and election-specific contest identity |
| Add governors, other statewide offices, ballot measures, or state legislatures | Broader state-power and administration context | Adds contest types, source reconciliation, and substantial editorial breadth; not silently included |

Recommend House/Senate as the base race scope, while the actions chronology can include a relevant governor, state legislature, election board, party organization, court, or federal agency even if its own office is outside the tracked contest set. A record’s relevance should explain that connection. A general election, primary, runoff, and special election must have separate identities; different contests for the same seat/term must not be merged. Delegates/nonvoting offices, where included, should be distinguished from voting House seats.

Recommend the election chronology cover **the 2026 cycle, with selected earlier antecedents when necessary to understand an ongoing action**. The exact historical boundary remains a user decision. Do not automatically reuse the protests’ agreed September 1 start: election rules, district plans, and lawsuits affecting November may originate earlier. Full backfill of every campaign development is not recommended for this initial scope.

For “updates,” I recommend sourced changes to maps, contest status, reported results when available, and reviewed institutional developments, with official-source links. The exact coverage and refresh cadence for displayed vote totals, and whether to show a named provider’s race calls, remain scope/source decisions. The initial product can be useful before voting concludes and remain useful through canvassing, certification, and subsequent disputes. Its visual design need not change identity across those stages.

## What official sources can actually supply

I independently inspected the primary sources below. This verifies published source availability/capabilities and a few material limitations, not a completed fifty-state acquisition pipeline or a validated dataset import. No accounts, API keys, paid access, or services were created.

| Need | Verified source capability | Product constraint |
|---|---|---|
| Federal calendar and source routing | FEC publishes the general-election date and primary information, directs readers to state offices for ballot access/results, and explicitly says its results are not immediately available. | Use FEC as a reference/directory and historical federal compilation, not as a live-results feed. State/local authorities govern the relevant details. [FEC](https://www.fec.gov/introduction-campaign-finance/election-results-and-voting-information/) |
| Candidates and basic contest information | North Carolina provides current 2026 candidate CSV/PDF lists with documented fields and update caveats. California provides a certified general-election candidate list. | Official formats and finality differ. A federal campaign-finance registration is not proof that a candidate appears on a state ballot. Store ballot-list source/version; omit irrelevant personal contact fields. [North Carolina](https://www.ncsbe.gov/results-data/candidate-lists), [California](https://www.sos.ca.gov/elections/upcoming-elections/general-election-november-3-2026/) |
| Congressional geography | Census provides 120th-Congress geographic products and explicit vintage/change notes. | “Newest file” is not automatically the operative election map. Verify state plans and legal applicability, and retain geometry versions. [Census congressional districts](https://www.census.gov/programs-surveys/decennial-census/about/rdo/congressional-districts.html) |
| Results and certification | EAC describes the move from unofficial reporting through canvassing/certification. North Carolina documents downloadable results and 5–10 minute dashboard updates after polls close. | The NC cadence is not a national guarantee. Officials’ preliminary tallies remain unofficial until certified; media projections are separate. [EAC](https://www.eac.gov/election-officials/election-results-canvass-and-certification), [NC dashboard documentation](https://www.ncsbe.gov/results-data/election-results/about-election-results-dashboard) |
| Federal legislation | Congress.gov’s API exposes bills, actions, amendments, text versions, and laws; API access uses a key. | A bill introduced or passed by one chamber is not an enacted law. Preserve the sequence and the text version relevant to each development. [Congress.gov API](https://api.congress.gov/) |
| Executive/agency actions | White House Presidential Actions provides first-party action documents. FederalRegister.gov offers API documentation and links to official legal editions on GovInfo. | A first-party document is evidence of an action or stated rationale, not independent proof of motive or effect. For legal text/status, follow the official edition and subsequent orders. [White House](https://www.whitehouse.gov/presidential-actions/), [Federal Register](https://www.federalregister.gov/developers/documentation/api/v1) |
| Litigation | Supreme Court provides docket search and orders; GovInfo provides a federal court-opinions collection; PACER provides federal court records with access fees possible. | No source inspected supplies a complete free feed of every federal/state election docket. Track selected matters through the relevant court and docket; missing documents/coverage must remain visible. [Supreme Court](https://www.supremecourt.gov/docket/docket.aspx), [GovInfo](https://www.govinfo.gov/help/uscourts), [PACER access costs](https://pacer.uscourts.gov/pacer-pricing-how-fees-work) |

Two live source observations materially sharpen the design:

**Boundary mismatch is already a real source risk.** The Census page currently warns that some Missouri 120th-Congress shapefile/geodatabase/GeoPackage products have not yet been regenerated to match the plan it identifies as operative for 2026, while the block equivalency data has been updated. This review is reporting Census’s published warning, not independently adjudicating the underlying litigation or validating those files. The implication is straightforward: record plan/version/applicability and verify the actual file used. A generic “2026” filename is insufficient. [Census warning](https://www.census.gov/programs-surveys/decennial-census/about/rdo/congressional-districts.html).

**A results URL existing before Election Day does not mean results exist.** The inspected North Carolina November 3 page is already titled unofficial general-election results but reports zero precincts/ballots and a pre-election upload timestamp. Those are not 2026 vote findings. The application must recognize pre-election/placeholder/test states and avoid presenting zeros as actual electoral outcomes. [NC November 3 results page](https://er.ncsbe.gov/?election_dt=11%2F03%2F2026).

This research supports a practical reviewed map/chronology module. It does not establish the feasibility or cost of nationwide live counts. Journalism remains useful for discovery, investigative context, and attributed claims; primary documents establish official actions/status when available. The chronology should retain disagreements and corrections, including evidence that weakens the initial hypothesis.

## Representing actions without assuming misconduct

Use an **action or proceeding record with chronological developments**, connected to actors, sources, and affected jurisdictions. A compact public card can carry the essential facts, with deeper fields available in detail:

- What happened: concise factual description, action type, responsible actor and office/organization at that time.
- Authority and scope: document/bill/order/docket identifier, issuing body, documented affected jurisdiction or contest, and any uncertain scope.
- Current state: proposed/adopted/withdrawn/superseded; whether and when effective; separately, challenged/stayed/enjoined/appealed/reversed where supported. A lawsuit filing does not itself suspend a measure.
- Rationale and evidence: what the actor says it is doing, who alleges a different purpose/effect, supporting and contradictory material, and the review date.
- Effect assessment: alleged, anticipated by an identified analyst, measured with a stated method, or found by a named adjudicative body. A procedural ruling is not automatically a final merits finding.

This can include redistricting, voting-administration changes, ballot-access disputes, executive/agency directives, litigation, certification actions, and documented pressure on officials when relevant and adequately sourced. These are proposed categories, not claims that a specific actor engaged in each behavior.

A useful card might say: “Agency issued directive; plaintiffs filed challenge; court temporarily blocked specified provision; appeal pending.” This is an illustrative record pattern, **not a factual allegation about a current case**. The title should not turn that sequence into “administration rigged election.” Conversely, an established finding should be stated accurately and not diluted to a mere dispute.

Keep actor identity precise: the White House, a federal agency, an official acting in office, a party committee, and an individual campaign are different actors. Party affiliation or shared policy does not prove coordination. Link related actions when a document, joint filing, common authority, or other evidence supports the link, rather than constructing a conspiracy network from shared timing.

For dates, distinguish announcement/signature/adoption, effective date or interval, filing, order, source publication, retrieval, and review. Store legal applicability separately from when the database learned of it. Changes may affect only parts of a measure or particular jurisdictions; a one-word “blocked” badge cannot safely replace that scope. The interface can summarize this without exposing a complicated schema to the reader.

## Shared storage, result states, and maintenance

Share geography infrastructure, actor identities where explicitly matched, source/evidence records, review history, chronology components, search, and publication tools. Add election-cycle/contest/seat/stage, ballot-candidate associations, boundary-plan versions, procedural developments, and optional result snapshots. A state/district display is a view over those records, not the authoritative store.

If results are included, store the reporting authority/provider, reporting unit, contest stage, snapshot time, vote measure, official certification status, and corrections. Distinguish **officially sourced but unofficial/provisional tallies**, **certified results**, **a named provider’s projection/call**, and **unavailable/not yet reported**. Never use “official” ambiguously for both source and finality. A map can show a certified result while also showing a pending contest/challenge, with each status accurately scoped.

Do not add county subtotals to an already statewide total; do not assume all precincts reporting means all eligible ballots counted. Candidate lists, boundary files, and results need validated identity mappings and stale-data checks. A decrease after a correction or a change as ballots are counted should first be represented as a sourced data update, not automatically classified as manipulation. EAC expressly explains that preliminary reporting changes before final certification. [EAC results guidance](https://www.eac.gov/where-do-i-find-election-results).

For the recommended simple module, daily editorial review during active periods, plus explicit checks after major official developments, is a reasonable planning proposal. Publish actual last-checked/source timestamps and gaps. Around November 3, plan reviewer availability and continued follow-through through certification. Exact service hours/refresh commitments remain unapproved. If unattended, the interface should say when it was last checked rather than imply continuous monitoring.

A live-results promise would add per-jurisdiction or licensed-provider integration, faster collection, load/rate-limit handling, result reconciliation, staffed incident response, and potentially data-license cost. It should not be smuggled into the phrase “updated map.” The biggest cost for the recommended initial module is likely source reconciliation and editorial/legal-status review, not polygon rendering. No price estimate or subscription is established by this research.

## Decisions and next review deliverables

The new established requirement is an election map plus chronological developments, with a focused investigation of administration/Republican election-related actions, fitting the same unified application patterns. The working cycle, race scope, historical start, results cadence, and breadth of action coverage remain recommendations or decisions.

Only four election-specific choices materially change the project:

1. **Race scope:** House/Senate baseline as recommended, state/Senate-only overview, or adding governor/other contests.
2. **Update commitment:** sourced evolving race/results status and reviewed developments as recommended; determine which vote totals/calls to include and whether their refresh must be near real time nationwide.
3. **Historical reach:** 2026 with necessary earlier antecedents as recommended, or a different explicit start.
4. **Deadline and review capacity:** an enduring research layer versus an election-day operational commitment, and who will review fast-changing actions/status. The addition should not silently displace the already promised conflict modernization or September protest backfill.

After the user agrees the three-domain direction, the separate planning stage should add just three concrete items to the original packet: **one desktop/mobile election map-and-timeline design using the shared components; a few sourced sample records covering a contest, boundary issue, and institutional action with a status change; and a small official-source coverage/refresh matrix.** Include examples of a national action, unavailable/pre-election results, disputed effects, and a stale source. This proves the actual addition without creating a separate product specification for every conceivable election feature.

The coherent project direction is now: **one evidence-led application for conflicts, protest mobilization, and U.S. election developments, with shared map/time/detail experiences and distinct factual models.** Keep the election module focused and understandable; strengthen boundary/version and action-status handling where accuracy requires it. Review this addition with the user, then proceed to the separate execution-planning stage. No implementation or remote changes have been made.
