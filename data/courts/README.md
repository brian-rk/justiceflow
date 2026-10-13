# Court register

`jmap_courts_snapshot.json` is a snapshot of the Judiciary of Tanzania's public court map ([jmap.judiciary.go.tz](https://jmap.judiciary.go.tz)) for the seven regions JusticeFlow models, plus Mtwara (whose High Court and Court of Appeal registry serve Lindi). It was fetched on 13 October 2026, one request per region, from the same public data service the map page uses.

[`../../justiceflow/courts.csv`](../../justiceflow/courts.csv) is built from it by `python -m justiceflow.build_courts` (add `--fetch` to refresh the snapshot). Each row is one court with its region, district, level, High Court division (if any), a short code used in case numbers, and its source.

The map is incomplete in a few places, so these courts are added from the instruments that establish them, and marked as such:

| Court | Source |
|---|---|
| Court of Appeal, Dar es Salaam (Main Registry); Arusha, Kigoma, Sumbawanga, Mtwara Court of Appeal registries | Tanzania Court of Appeal (Sub-registries) Order, GN 579 of 2020 |
| Lindi's High Court cases go to the Mtwara High Court | High Court Registries (Amendment) Rules 2023, GN 853A |
| Dodoma Resident Magistrate's Court | Magistrates' Courts Act schedule (one RM court per region) |

Known gaps in the map that are **not** filled: it lists no District Court for Lindi district or Dodoma city, so cases there use the other District Courts of the region. To cover all 26 Mainland regions, add them to `REGIONS` in `build_courts.py` and to `config.REGIONS`, then rebuild.
