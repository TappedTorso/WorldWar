WorldWar contextual map geometry

countries-110m.json: world-atlas 2.0.2, derived from Natural Earth 1:110m Admin 0 country boundaries. Natural Earth data is public domain. https://www.naturalearthdata.com/about/terms-of-use/ and https://github.com/topojson/world-atlas . Package license reproduced in LICENSE-world-atlas.

states-10m.json: us-atlas 3.0.1, derived from U.S. Census Bureau cartographic boundary files. https://github.com/topojson/us-atlas . Package license reproduced in LICENSE-us-atlas.

State outlines are geographic context, NOT 2026 congressional districts. No district plan/vintage is represented by this asset. House records without a separately verified, version-matched district geometry asset group at state level. Country boundaries are contextual and do not imply endorsement of a territorial claim. Geometry is locally bundled; no external runtime map, font, or CDN dependency.


districts-2026.geojson: 435 voting U.S. House districts, simplified for display from official U.S. Census Bureau TIGER/Line 2026 CD120 (49 states) and TIGER/Line 2025 CD119 for Missouri's eight seats. Census states that Missouri's CD120 GIS had not been regenerated and the operative plan is unchanged from 2022/2024. Canonical coordinates are RFC 7946 longitude/latitude WGS84. The renderer normalizes ring winding on a copy for D3, after validating the contest identity and plan vintage. Source URLs, retrieval dates, input ZIP hashes, transformation/precision notes, the Missouri exception, and public-domain attribution are in districts-attribution.json. Display geometry is unsuitable for address assignment, legal boundary adjudication or area calculation. Authority: https://www.census.gov/programs-surveys/decennial-census/about/rdo/congressional-districts.html . No winners, party affiliations or electoral effects are inferred from shapes.
