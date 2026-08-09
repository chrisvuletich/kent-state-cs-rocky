from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.test_support import BackendTestCase, main


class TelemetryAnalyticsEndpointTests(BackendTestCase):
    def setUp(self):
        super().setUp()
        main.telemetry_interactions.delete_many({})
        main.telemetry_current.delete_many({})
        self.now = datetime.now(timezone.utc).replace(microsecond=0)
        self._insert_rows()

    def row(self, request_id, minutes_ago, outcome=None, *, user="student-1",
            course=44001, tokens=(10, 5), latency=100, flagged=False,
            source="public_api", prompt=None, operation="responses.create",
            inference_dispatched=None):
        if inference_dispatched is None:
            inference_dispatched = outcome in {"completed", "failed", "timed_out"}
        document = {
            "_id": request_id,
            "request_id": request_id,
            "schema_version": 2,
            "state": "terminal" if outcome else "received",
            "received_at": self.now - timedelta(minutes=minutes_ago),
            "source": source,
            "operation": operation,
            "actor": {
                "user_id": user,
                "email": f"{user}@kent.edu" if user else None,
                "name": f"User {user}" if user else None,
            },
            "credential": {"key_id": f"key-{user or 'group'}", "key_name": "key-1"},
            "course": {"course_id": course, "course_code": "CS-44001", "group_id": None},
            "request": {"input_text": prompt or f"prompt {request_id}", "model": "rocky"},
            "usage": {
                "input_tokens": tokens[0],
                "output_tokens": tokens[1],
                "total_tokens": sum(tokens),
            },
            "performance": {"request_latency_ms": latency},
            "model": {"actual_model": "granite-test", "public_model": "rocky"},
            "review": {"flagged": flagged, "status": "unreviewed"},
        }
        if inference_dispatched:
            document["inference_dispatched_at"] = document["received_at"]
        if outcome:
            document.update({
                "outcome": outcome,
                "terminal_at": document["received_at"] + timedelta(milliseconds=latency),
                "http_status": 200 if outcome == "completed" else 500,
                "response": {"output_text": f"response {request_id}"},
            })
        if outcome == "completed":
            document["performance"].update({
                "model_total_duration_ns": 2_000_000_000,
                "model_load_duration_ns": 100_000_000,
                "prompt_eval_duration_ns": 500_000_000,
                "generation_duration_ns": 1_000_000_000,
            })
        return document

    def _insert_rows(self):
        main.telemetry_interactions.insert_many([
            self.row("req_complete_1", 5, "completed", tokens=(10, 5), latency=100),
            self.row("req_complete_2", 10, "completed", user="student-2", tokens=(20, 10), latency=300, flagged=True),
            self.row("req_failed", 20, "failed", tokens=(5, 0), latency=500),
            self.row("req_rejected", 30, "rejected", user=None, course=None, tokens=(0, 0), latency=50),
            self.row("req_active", 2, None, tokens=(0, 0), latency=None),
            self.row("req_old", 60 * 25, "completed", tokens=(999, 999)),
        ])

    def test_summary_reports_real_request_token_rate_and_latency_metrics(self):
        response = self.client.get(
            "/analytics/summary?window=24h", headers=self.admin_headers
        )
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()

        self.assertEqual(payload["requests"], 5)
        self.assertEqual(payload["outcomes"], {
            "completed": 2,
            "rejected": 1,
            "failed": 1,
            "timed_out": 0,
        })
        self.assertEqual(payload["active"], 1)
        self.assertEqual(payload["flagged"], 1)
        self.assertEqual(payload["usage"], {
            "input_tokens": 35,
            "output_tokens": 15,
            "total_tokens": 50,
            "input_bytes": 0,
            "output_bytes": 0,
        })
        self.assertEqual(payload["success_rate"], 0.6667)
        self.assertEqual(payload["acceptance_rate"], 0.8)
        self.assertEqual(payload["api_latency_ms"]["average"], 237.5)
        self.assertEqual(payload["latency_ms"]["average"], 300.0)
        self.assertEqual(payload["generation"]["requests"], 5)
        self.assertEqual(payload["generation"]["inference_dispatches"], 3)
        self.assertEqual(payload["rates"]["peak_requests_per_minute"], 1)
        self.assertEqual(payload["rates"]["peak_tokens_per_minute"], 30)
        self.assertEqual(
            payload["model_performance"]["generation_tokens_per_second"],
            7.5,
        )
        self.assertEqual(
            payload["model_performance"]["prompt_eval_duration"]["average_ms"],
            500.0,
        )

    def test_current_reports_live_and_lifetime_counters(self):
        main.telemetry_current.insert_one({
            "_id": "rocky:model-runtime",
            "interactions_received_total": 90,
            "interactions_completed_total": 80,
            "interactions_rejected_total": 3,
            "interactions_failed_total": 5,
            "interactions_timed_out_total": 2,
            "active_requests": 4,
            "prompt_tokens_total": 1_200,
            "output_tokens_total": 800,
            "request_latency_ms_total": 1_000,
            "request_latency_samples_total": 4,
            "last_model": "granite-test",
        })
        response = self.client.get(
            "/analytics/current", headers=self.admin_headers
        )
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["active_requests"], 1)
        self.assertEqual(payload["lifetime"]["requests"], 90)
        self.assertEqual(payload["lifetime"]["usage"]["input_tokens"], 1_200)
        self.assertEqual(payload["lifetime"]["latency_ms"]["average"], 250.0)
        self.assertEqual(payload["last_model"], "granite-test")

    def test_my_usage_is_scoped_to_authenticated_user(self):
        student_id = self.seeded_user_ids["student.local@kent.edu"]
        own_recent = self.row("req_my_recent", 3, "completed", tokens=(12, 7))
        own_recent["actor"] = {
            "user_id": student_id,
            "email": "student.local@kent.edu",
            "name": "Student Local",
        }
        own_older = self.row("req_my_older", 60 * 48, "failed", tokens=(5, 0))
        own_older["actor"] = {
            "user_id": student_id,
            "email": "student.local@kent.edu",
            "name": "Student Local",
        }
        main.telemetry_interactions.insert_many([own_recent, own_older])

        response = self.client.get("/analytics/my-usage", headers=self.student_headers)
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["total_requests"], 2)
        self.assertEqual(payload["requests_today"], 1)
        self.assertEqual(payload["usage"]["input_tokens"], 17)
        self.assertEqual(payload["usage"]["output_tokens"], 7)
        self.assertEqual(payload["outcomes"]["completed"], 1)
        self.assertEqual(payload["outcomes"]["failed"], 1)

    def test_my_usage_requires_authenticated_identity(self):
        response = self.client.get("/analytics/my-usage")
        self.assertEqual(response.status_code, 401)

    def test_timeseries_includes_zero_buckets_and_totals(self):
        response = self.client.get(
            "/analytics/timeseries?window=1h&bucket=minute",
            headers=self.admin_headers,
        )
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["bucket"], "minute")
        self.assertGreaterEqual(len(payload["buckets"]), 60)
        self.assertEqual(sum(row["requests"] for row in payload["buckets"]), 5)
        self.assertEqual(
            sum(row["usage"]["total_tokens"] for row in payload["buckets"]),
            50,
        )

    def test_breakdowns_cover_user_course_key_model_source_and_outcome(self):
        for dimension in ("user", "course", "key", "group", "model", "source", "outcome"):
            response = self.client.get(
                f"/analytics/breakdown?window=24h&dimension={dimension}",
                headers=self.admin_headers,
            )
            self.assertEqual(response.status_code, 200, dimension)
            payload = response.get_json()
            self.assertEqual(payload["dimension"], dimension)
            self.assertGreater(len(payload["rows"]), 0)
            self.assertEqual(sum(row["requests"] for row in payload["rows"]), 5)

        users = self.client.get(
            "/analytics/breakdown?dimension=user", headers=self.admin_headers
        ).get_json()["rows"]
        self.assertEqual(users[0]["id"], "student-1@kent.edu")
        self.assertEqual(users[0]["requests"], 3)
        self.assertTrue(any(row["id"] == "unattributed" for row in users))

    def test_model_listing_is_api_traffic_not_generation_traffic(self):
        self.telemetry_model_row = self.row(
            "req_models",
            1,
            "completed",
            tokens=(0, 0),
            latency=15,
            operation="models.list",
            inference_dispatched=False,
        )
        main.telemetry_interactions.insert_one(self.telemetry_model_row)

        payload = self.client.get(
            "/analytics/summary?window=24h", headers=self.admin_headers
        ).get_json()

        self.assertEqual(payload["requests"], 6)
        self.assertEqual(payload["outcomes"]["completed"], 3)
        self.assertEqual(payload["generation"]["requests"], 5)
        self.assertEqual(payload["generation"]["outcomes"]["completed"], 2)
        self.assertEqual(payload["latency_ms"]["samples"], 3)
        self.assertEqual(payload["api_latency_ms"]["samples"], 5)

        filtered = self.client.get(
            "/analytics/summary?window=24h&operation=models.list",
            headers=self.admin_headers,
        ).get_json()
        self.assertEqual(filtered["requests"], 1)
        self.assertEqual(filtered["generation"]["requests"], 0)

    def test_recent_filters_and_detail_return_complete_stored_content(self):
        response = self.client.get(
            "/analytics/requests?outcome=completed&user_id=student-2&flagged=true",
            headers=self.admin_headers,
        )
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["matched"], 1)
        self.assertEqual(payload["requests"][0]["request_id"], "req_complete_2")
        self.assertNotIn("request", payload["requests"][0])

        detail = self.client.get(
            "/analytics/requests/req_complete_2", headers=self.admin_headers
        )
        self.assertEqual(detail.status_code, 200)
        detail_payload = detail.get_json()
        self.assertEqual(detail_payload["request"]["input_text"], "prompt req_complete_2")
        self.assertEqual(detail_payload["response"]["output_text"], "response req_complete_2")
        self.assertNotIn("_id", detail_payload)

    def test_shared_filters_apply_to_summary_breakdown_and_request_queue(self):
        route = (
            "/analytics/summary?window=24h&user_id=student-2@kent.edu"
            "&course_id=CS-44001&key_id=key-student-2&model=granite-test"
            "&source=public_api&operation=responses.create&outcome=completed&flagged=true"
        )
        summary_payload = self.client.get(route, headers=self.admin_headers).get_json()
        self.assertEqual(summary_payload["requests"], 1)
        self.assertEqual(summary_payload["outcomes"]["completed"], 1)

        breakdown_payload = self.client.get(
            route.replace("/analytics/summary", "/analytics/breakdown")
            + "&dimension=user",
            headers=self.admin_headers,
        ).get_json()
        self.assertEqual(len(breakdown_payload["rows"]), 1)
        self.assertEqual(breakdown_payload["rows"][0]["id"], "student-2@kent.edu")

        request_payload = self.client.get(
            route.replace("/analytics/summary", "/analytics/requests"),
            headers=self.admin_headers,
        ).get_json()
        self.assertEqual(request_payload["matched"], 1)
        self.assertEqual(request_payload["requests"][0]["request_id"], "req_complete_2")

    def test_analytics_exports_are_admin_only_exact_and_audited(self):
        row = self.row("req_export", 1, "completed", user="student-export")
        row["request"]["input_text"] = "=PROMPT(1)"
        row["response"]["output_text"] = "+response"
        main.telemetry_interactions.insert_one(row)

        denied = self.client.get(
            "/analytics/export?format=json&window=24h", headers=self.student_headers
        )
        self.assertEqual(denied.status_code, 403)

        exported = self.client.get(
            "/analytics/export?format=json&window=24h&user_id=student-export",
            headers=self.admin_headers,
        )
        self.assertEqual(exported.status_code, 200)
        self.assertIn("attachment", exported.headers["Content-Disposition"])
        payload = exported.get_json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["records"][0]["prompt"], "=PROMPT(1)")
        self.assertEqual(payload["records"][0]["response"], "+response")

        csv_export = self.client.get(
            "/analytics/export?format=csv&window=24h&user_id=student-export",
            headers=self.admin_headers,
        )
        self.assertEqual(csv_export.status_code, 200)
        csv_text = csv_export.get_data(as_text=True)
        self.assertIn("'=PROMPT(1)", csv_text)
        self.assertIn("'+response", csv_text)
        self.assertTrue(any(
            row.get("event_type") == "analytics-export"
            for row in main.api_history.find({})
        ))

        too_large = self.client.get(
            "/analytics/export?format=json&window=24h&limit=1",
            headers=self.admin_headers,
        )
        self.assertEqual(too_large.status_code, 413)
        self.assertIn("add filters", too_large.get_json()["error"])

    def test_routes_are_admin_only_and_query_inputs_are_bounded(self):
        routes = (
            "/analytics/kpis",
            "/analytics/activity",
            "/analytics/summary",
            "/analytics/current",
            "/analytics/timeseries",
            "/analytics/breakdown",
            "/analytics/requests",
            "/analytics/requests/req_complete_1",
            "/analytics/export",
        )
        for route in routes:
            response = self.client.get(route, headers=self.student_headers)
            self.assertEqual(response.status_code, 403, route)

        invalid = (
            "/analytics/summary?window=forever",
            "/analytics/timeseries?window=30d&bucket=minute",
            "/analytics/breakdown?dimension=prompt",
            "/analytics/breakdown?limit=1000",
            "/analytics/requests?limit=1000",
            "/analytics/requests?outcome=unknown",
            "/analytics/requests?flagged=perhaps",
            "/analytics/summary?operation=not-real",
        )
        for route in invalid:
            response = self.client.get(route, headers=self.admin_headers)
            self.assertEqual(response.status_code, 400, route)
            self.assertIn("error", response.get_json())

        missing = self.client.get(
            "/analytics/requests/req_missing", headers=self.admin_headers
        )
        self.assertEqual(missing.status_code, 404)

    def test_legacy_accepted_at_records_remain_queryable(self):
        main.telemetry_interactions.insert_one({
            "_id": "legacy",
            "state": "terminal",
            "outcome": "completed",
            "accepted_at": self.now - timedelta(minutes=3),
            "prompt_eval_count": 4,
            "eval_count": 2,
            "request_latency_ms": 20,
        })
        payload = self.client.get(
            "/analytics/summary?window=1h", headers=self.admin_headers
        ).get_json()
        self.assertEqual(payload["requests"], 6)
        self.assertEqual(payload["usage"]["total_tokens"], 56)

    def test_compatibility_endpoints_are_live_not_seeded(self):
        kpis = self.client.get(
            "/analytics/kpis?window=24h", headers=self.admin_headers
        ).get_json()
        activity = self.client.get(
            "/analytics/activity?window=1h&bucket=hour",
            headers=self.admin_headers,
        ).get_json()
        self.assertEqual(kpis[0]["value"], "5")
        self.assertEqual(kpis[3]["value"], "50")
        self.assertEqual(sum(row["requests"] for row in activity), 5)


if __name__ == "__main__":
    import unittest

    unittest.main()
