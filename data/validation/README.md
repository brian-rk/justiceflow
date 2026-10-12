# Real-case test

Does the risk model, trained only on synthetic data, say anything useful about real Tanzanian cases? This folder holds the test and its result.

**Short answer: not yet.** On 56 real decided cases the model ranks slow cases above fast ones no better than simply knowing which court the case is in (AUC 0.65 vs 0.71), it rates none of the 20 overruns High, and within one court it does no better than chance. Real case data from the Judiciary is needed before the risk scores mean anything for a single case. Details are in [RESULTS.md](RESULTS.md).

## How the sample was collected

TanzLII forbids scraping and blocks automated page reads (a direct fetch returns HTTP 403), so no TanzLII page was downloaded. Instead, the cases were taken from **web search results that list TanzLII judgments**. For each judgment the search listing shows:

* the **case name and number**, e.g. *Land Case No. 38 of 2021*. A Tanzanian case number carries the year it was filed;
* the **court** (from the neutral citation: TZCA = Court of Appeal, TZHC = High Court, TZHCLandD = Land Division, and so on);
* the **decision date**, which is also part of the TanzLII address (`.../eng@2024-04-02`).

Each row in [tanzlii_search_sample.csv](tanzlii_search_sample.csv) keeps its TanzLII link, so anyone can open the judgment and check it. Rows were not checked against the judgment text.

**Labels without exact filing dates.** With only the filing year, a case could have been filed on any day of that year. The label "took longer than the disposition target" is used only when it is the same for the earliest and the latest possible filing day. For example, *Land Case No. 38 of 2021*, decided on 2 April 2024, took at least 27 months whatever its filing day, so it overran the High Court's 24-month target. Cases where the year alone cannot decide the label are kept in the file but left out of the scores (10 of 66). The code is `interval_labels` in [justiceflow/ingest.py](../../justiceflow/ingest.py).

## Run it

```
python -m justiceflow.check_tanzlii data/validation/tanzlii_search_sample.csv --report data/validation/RESULTS.md
# or test the model the web app is using:
python -m justiceflow.check_tanzlii data/validation/tanzlii_search_sample.csv --model backend/model_store/model_1.joblib
```

## What the result means

* **Recalibrating to 2025 helped, but only through the court level.** The same test with the old 2020-calibrated model gives AUC 0.48, worse than a coin toss. The 2025 calibration puts the long delays where they really are, at the Court of Appeal.
* **The model adds nothing beyond the court level.** A predictor that only knows the court gets 0.71. Within the High Court the model gives every case about 0% risk (the 2025 High Court backlog is only 1.2%), yet 9 of the 40 High Court cases here overran. Small changes to the synthetic data move the model's real-case score by several points (0.69 and 0.65 in two runs this week), which is what you would expect if it has no real signal of its own.
* **The real cases show patterns the synthetic data lacks.** In this sample, High Court land and probate cases overran most often (38% and 50%), and cases with more parties overran more (42% with four or more parties, 32% with fewer). The synthetic generator does not build these in, so the model cannot learn them.
* **Representation was not in the search listings.** Every row assumes the parties had advocates (usual at these courts). Assuming nobody did gives 0.66, about the same, so this guess does not change the conclusion.

## Limits of this sample

* **Only High Court and Court of Appeal cases.** Primary, District and Resident Magistrate courts do not publish judgments on TanzLII in a way search can reach, and their dates appear only inside High Court appeal judgments.
* **It is skewed toward slow cases.** TanzLII holds cases that ended in a written judgment, which tend to be contested and long. Withdrawals and quick settlements are missing, and the overrun rate here (36%) is far above the Judiciary's 5% backlog.
* **56 cases is small.** The 95% range on the AUC is wide (0.53 to 0.84).
* **Party counts are approximate** where a title says "& Others" (counted as two).

## What would make the test real

1. **An anonymised extract from the Judiciary's e-CMS** (request letter: [../requests/Judiciary_data_request.md](../requests/Judiciary_data_request.md)), with filing and decision dates, hearings and adjournment reasons, for all courts. This is the only way to train and test the model on Tanzanian reality.
2. **A hand-collected TanzLII sample with exact dates** (guide: [../TANZLII_COLLECTION_GUIDE.md](../TANZLII_COLLECTION_GUIDE.md)), including High Court appeals that state the subordinate court's dates.
3. **TanzLII bulk access** ([../requests/TanzLII_bulk_access_request.md](../requests/TanzLII_bulk_access_request.md)).

Until then, present the risk score as a demonstration of the workflow, not as a validated prediction.
