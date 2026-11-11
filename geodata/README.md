# Bundled OpenStreetMap demo data

Small, real OpenStreetMap extracts used by `signaldesk_map_scan` when the network is
off (`SIGNALDESK_OFFLINE=1`) or every Overpass instance fails. Each file records the
exact Overpass query, the instance it came from, and the fetch date.

| File | Area | OSM tag | Elements |
|---|---|---|---|
| `zurich_dentist.json` | Zürich, Switzerland | `amenity=dentist` | 40 |
| `zurich_cafe.json` | Zürich, Switzerland | `amenity=cafe` | 40 |

Only a few tags per element are kept (name, address, website, email, phone, opening hours).

**Data © OpenStreetMap contributors, available under the Open Database License (ODbL) 1.0.**
https://www.openstreetmap.org/copyright. If you redistribute these files or a database
derived from them, keep the attribution and share-alike terms.
