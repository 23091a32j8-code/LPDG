# Decisions

Part 2 area: **software development**.

1. **Materialised output after `POST /run`.** The alternative was calculating every ranking in `GET /rankings`. Materialising makes reads fast and reproducible for the small operations team; the explicit rerun is the freshness boundary. A temporary file followed by atomic replacement prevents a reader seeing a partial CSV.
2. **One rerun defaults to all eight weeks.** The alternative was requiring a week parameter. The full run produces the required 120-row hand-in artifact; a week parameter is still available for operational reruns and live debugging.
3. **Transparent recency/offline baseline.** The alternative was a black-box trained model. The selected score prioritises stale telemetry and raises the priority when an explicit offline signal is present, which an operator can understand. It may miss faults with fresh but misleading telemetry; it must be evaluated against the supplied baseline and data before submission.
4. **UTC Monday cutoff.** The alternative was Berlin-local midnight. UTC matches the published baseline guidance and is applied uniformly to every telemetry record. The consequence is a small boundary difference near daylight-saving changes.
5. **Standard-library HTTP server plus replaceable ranker.** The alternative was coupling a framework handler directly to ranking code. A small dependency surface is easier to run offline; `RankingStrategy` is the seam for a baseline-compatible or learned ranker. It intentionally does not provide authentication because the brief describes a local operations team, not public internet access.

