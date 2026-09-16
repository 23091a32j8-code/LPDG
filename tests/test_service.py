import tempfile
import threading
import unittest
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from lpdg_health.api import build_service, create_handler
from lpdg_health.ranker import WEEK_STARTS


class RankingServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        telemetry = root / "data" / "telemetry" / "month=2026-01"
        telemetry.mkdir(parents=True)
        rows = []
        for number in range(16):
            gateway = f"GW-{number:02d}"
            for day in range(60):
                rows.append({"gateway_id": gateway, "timestamp": (date(2025, 12, 1) + timedelta(days=day - number)).isoformat(), "offline_hours": number})
        pd.DataFrame(rows).to_csv(telemetry / "telemetry.csv", index=False)
        self.service = build_service(root / "data", root / "runtime")

    def tearDown(self):
        self.temp.cleanup()

    def test_full_run_writes_validator_shaped_csv(self):
        result = self.service.run()
        output = pd.read_csv(self.service.predictions_path)
        self.assertEqual(result["rows"], 120)
        self.assertEqual(len(output), 120)
        self.assertEqual(set(output.columns), {"week_start", "gateway_id", "rank", "score", "reason"})
        self.assertEqual(set(output[output.week_start == str(WEEK_STARTS[0])]["rank"]), set(range(1, 16)))

    def test_explanation_is_from_materialised_ranking(self):
        self.service.run(WEEK_STARTS[0])
        ranking = self.service.rankings(WEEK_STARTS[0])
        self.assertEqual(self.service.explanation(ranking[0]["gateway_id"], WEEK_STARTS[0])["rank"], 1)

    def test_http_contract_runs_and_returns_a_ranking(self):
        from http.server import ThreadingHTTPServer
        from urllib.request import Request, urlopen

        server = ThreadingHTTPServer(("127.0.0.1", 0), create_handler(self.service))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_port}"
            request = Request(base + "/run", data=b"{}", method="POST", headers={"Content-Type": "application/json"})
            self.assertEqual(urlopen(request).status, 200)
            response = urlopen(base + f"/rankings?week_start={WEEK_STARTS[0]}")
            self.assertEqual(response.status, 200)
            self.assertEqual(len(__import__("json").loads(response.read())), 15)
        finally:
            server.shutdown()
            server.server_close()
