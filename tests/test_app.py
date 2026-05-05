import io
import json
import unittest

from fastapi.testclient import TestClient

from server.main import app


DEFAULT_TIMESLOTS = [
    "2026-06-10 09:00",
    "2026-06-10 14:00",
]


class AppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_homepage_serves_html(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Intelligent University Exam Scheduling", response.text)

    def test_benchmark_catalog_lists_benchmark_1(self):
        response = self.client.get("/api/benchmarks")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        benchmark_ids = [item["id"] for item in payload["benchmarks"]]
        self.assertIn("1", benchmark_ids)

    def test_benchmark_dataset_can_be_loaded(self):
        response = self.client.get("/api/benchmarks/1")

        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual(payload["meta"]["id"], "1")
        self.assertGreater(len(payload["courses"]), 0)
        self.assertGreater(len(payload["students"]), 0)
        self.assertGreater(len(payload["rooms"]), 0)
        self.assertGreater(len(payload["timeslots"]), 0)
        self.assertEqual(
            {"greedy", "csp", "ga", "a_star"},
            set(payload["meta"]["available_algorithms"]),
        )

    def test_csv_upload_parses_expected_shape(self):
        csv_contents = "\n".join(
            [
                "course_code,course_name,enrollment,student_id,room_name,room_capacity,timeslot",
                "CS101,Intro to CS,180,STU001,Amphi 1,220,2026-06-10 09:00",
                "CS101,Intro to CS,180,STU002,Amphi 1,220,2026-06-10 09:00",
                "MATH202,Calculus II,150,STU001,Hall C,150,2026-06-10 14:00",
            ]
        ).encode("utf-8")

        response = self.client.post(
            "/api/upload-csv",
            files={"file": ("sample.csv", io.BytesIO(csv_contents), "text/csv")},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual(len(payload["courses"]), 2)
        self.assertEqual(len(payload["students"]), 2)
        self.assertEqual(len(payload["rooms"]), 2)
        self.assertIn("2026-06-10 09:00", payload["timeslots"])

    def test_greedy_schedule_stream_returns_result(self):
        payload = {
            "courses": [
                {"code": "CS101", "name": "Intro to CS", "enrollment": 2},
                {"code": "MATH202", "name": "Calculus II", "enrollment": 1},
            ],
            "students": [
                {"id": "STU001", "courses": ["CS101", "MATH202"]},
                {"id": "STU002", "courses": ["CS101"]},
            ],
            "rooms": [
                {"name": "Amphi 1", "capacity": 220},
                {"name": "Hall C", "capacity": 150},
            ],
            "timeslots": [{"date": value} for value in DEFAULT_TIMESLOTS],
        }

        response = self.client.post("/api/schedule/greedy", json=payload)

        self.assertEqual(response.status_code, 200)
        self.assertIn("event: result", response.text)

        result_payload = None
        current_event = None
        for line in response.text.splitlines():
            if line.startswith("event: "):
                current_event = line.split(": ", maxsplit=1)[1]
            elif line.startswith("data: ") and current_event == "result":
                result_payload = json.loads(line.split(": ", maxsplit=1)[1])
                break

        self.assertIsNotNone(result_payload)
        self.assertEqual(result_payload["algorithm"], "Greedy (Largest Enrollment First)")
        self.assertGreaterEqual(len(result_payload["assignments"]), 1)

    def test_infeasible_csp_stream_returns_partial_result(self):
        payload = {
            "courses": [
                {"code": "CS101", "name": "Intro to CS", "enrollment": 1},
                {"code": "MATH202", "name": "Calculus II", "enrollment": 1},
            ],
            "students": [
                {"id": "STU001", "courses": ["CS101", "MATH202"]},
            ],
            "rooms": [
                {"name": "Room 1", "capacity": 10},
            ],
            "timeslots": [{"date": "2026-06-10 09:00"}],
            "time_limit_sec": 0.05,
        }

        response = self.client.post("/api/schedule/csp", json=payload)

        self.assertEqual(response.status_code, 200)
        self.assertIn("event: result", response.text)

        result_payload = None
        current_event = None
        for line in response.text.splitlines():
            if line.startswith("event: "):
                current_event = line.split(": ", maxsplit=1)[1]
            elif line.startswith("data: ") and current_event == "result":
                result_payload = json.loads(line.split(": ", maxsplit=1)[1])
                break

        self.assertIsNotNone(result_payload)
        self.assertEqual(len(result_payload["assignments"]), 1)

    def test_infeasible_astar_stream_returns_partial_result(self):
        payload = {
            "courses": [
                {"code": "CS101", "name": "Intro to CS", "enrollment": 1},
                {"code": "MATH202", "name": "Calculus II", "enrollment": 1},
            ],
            "students": [
                {"id": "STU001", "courses": ["CS101", "MATH202"]},
            ],
            "rooms": [
                {"name": "Room 1", "capacity": 10},
            ],
            "timeslots": [{"date": "2026-06-10 09:00"}],
            "time_limit_sec": 0.05,
        }

        response = self.client.post("/api/schedule/a_star", json=payload)

        self.assertEqual(response.status_code, 200)
        self.assertIn("event: result", response.text)

        result_payload = None
        current_event = None
        for line in response.text.splitlines():
            if line.startswith("event: "):
                current_event = line.split(": ", maxsplit=1)[1]
            elif line.startswith("data: ") and current_event == "result":
                result_payload = json.loads(line.split(": ", maxsplit=1)[1])
                break

        self.assertIsNotNone(result_payload)
        self.assertEqual(len(result_payload["assignments"]), 1)


if __name__ == "__main__":
    unittest.main()
