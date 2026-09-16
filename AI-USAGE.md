# AI usage

An AI coding assistant was used to turn the FAQ contract into repository structure, documentation, a small HTTP API, and synthetic tests. The supplied LPDG data was not uploaded or shared.

One issue caught during review: a first-pass design would have read telemetry only at process startup. That conflicts with the FAQ's live-session requirement that `POST /run` see a newly mounted monthly partition without restarting. The implemented ranker reads the data afresh on every rerun, and the API's output replacement is atomic.

