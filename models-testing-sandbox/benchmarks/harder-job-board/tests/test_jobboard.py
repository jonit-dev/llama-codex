import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

from jobboard import JobStore, create_app


class JobStoreTests(unittest.TestCase):
    def make_store(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        return JobStore(Path(directory.name) / "jobs.sqlite")

    def test_crud_filters_search_and_persistence(self):
        store = self.make_store()
        job = store.create_job(
            " Backend Engineer ",
            " Acme ",
            "Build APIs and workers",
            tags=["Python", "api", " PYTHON "],
            remote=True,
        )

        self.assertEqual(job["id"], 1)
        self.assertEqual(job["title"], "Backend Engineer")
        self.assertEqual(job["company"], "Acme")
        self.assertEqual(job["status"], "draft")
        self.assertEqual(job["tags"], ["api", "python"])
        self.assertTrue(job["remote"])

        reopened = JobStore(store.path)
        self.assertEqual(reopened.get_job(1)["company"], "Acme")
        self.assertEqual([item["id"] for item in reopened.list_jobs(tag="PYTHON")], [1])
        self.assertEqual([item["id"] for item in reopened.list_jobs(remote=True)], [1])
        self.assertEqual([item["id"] for item in reopened.search_jobs("workers")], [1])

        updated = reopened.update_job(1, title="Senior Backend Engineer", tags=["platform"])
        self.assertEqual(updated["title"], "Senior Backend Engineer")
        self.assertEqual(updated["tags"], ["platform"])

    def test_status_transitions_and_validation(self):
        store = self.make_store()

        with self.assertRaises(ValueError):
            store.create_job("", "Acme", "desc")
        with self.assertRaises(ValueError):
            store.create_job("Role", "", "desc")
        with self.assertRaises(ValueError):
            store.create_job("Role", "Acme", "")

        job = store.create_job("Role", "Acme", "desc")
        self.assertEqual(store.transition_job(job["id"], "open")["status"], "open")
        self.assertEqual(store.transition_job(job["id"], "closed")["status"], "closed")
        self.assertEqual(store.transition_job(job["id"], "archived")["status"], "archived")

        other = store.create_job("Other", "Acme", "desc")
        with self.assertRaises(ValueError):
            store.transition_job(other["id"], "closed")
        with self.assertRaises(ValueError):
            store.transition_job(other["id"], "missing")
        with self.assertRaises(ValueError):
            store.update_job(other["id"], status="open")

        self.assertEqual([item["id"] for item in store.list_jobs(status="archived")], [1])

    def test_import_export_validation(self):
        store = self.make_store()

        with self.assertRaises(ValueError):
            store.import_jobs("not-json")
        with self.assertRaises(ValueError):
            store.import_jobs(json.dumps({"jobs": [{"title": "bad"}]}))

        store.create_job("One", "Acme", "Alpha", tags=["a"], remote=True)
        opened = store.transition_job(1, "open")
        self.assertEqual(opened["status"], "open")

        payload = store.export_jobs()
        data = json.loads(payload)
        self.assertEqual(data["jobs"][0]["title"], "One")
        self.assertTrue(data["jobs"][0]["remote"])

        other = self.make_store()
        imported = other.import_jobs(payload)
        self.assertEqual(imported, 1)
        self.assertEqual(other.list_jobs(status="open")[0]["tags"], ["a"])
        self.assertTrue(other.list_jobs(status="open")[0]["remote"])


class JobHttpTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.store = JobStore(Path(self.directory.name) / "jobs.sqlite")
        self.server = create_app(self.store)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.host, self.port = self.server.server_address

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.directory.cleanup()

    def request(self, method, path, body=None):
        headers = {}
        payload = None
        if body is not None:
            payload = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        conn = HTTPConnection(self.host, self.port, timeout=2)
        try:
            conn.request(method, path, payload, headers)
            response = conn.getresponse()
            raw = response.read().decode("utf-8")
            data = json.loads(raw) if raw else None
            return response.status, data
        finally:
            conn.close()

    def test_http_routes(self):
        status, data = self.request("GET", "/health")
        self.assertEqual((status, data), (200, {"status": "ok"}))

        status, created = self.request(
            "POST",
            "/jobs",
            {
                "title": "HTTP Engineer",
                "company": "Acme",
                "description": "Searchable service work",
                "tags": ["API"],
                "remote": True,
            },
        )
        self.assertEqual(status, 201)
        self.assertEqual(created["id"], 1)

        status, transitioned = self.request("POST", "/jobs/1/transition", {"status": "open"})
        self.assertEqual(status, 200)
        self.assertEqual(transitioned["status"], "open")

        status, listed = self.request("GET", "/jobs?status=open&tag=api&remote=true")
        self.assertEqual(status, 200)
        self.assertEqual([item["title"] for item in listed["jobs"]], ["HTTP Engineer"])

        status, searched = self.request("GET", "/search?q=service")
        self.assertEqual(status, 200)
        self.assertEqual([item["id"] for item in searched["jobs"]], [1])

        status, exported = self.request("GET", "/export")
        self.assertEqual(status, 200)
        self.assertEqual(exported["jobs"][0]["company"], "Acme")

        status, error = self.request("GET", "/missing")
        self.assertEqual((status, error), (404, {"error": "not found"}))


if __name__ == "__main__":
    unittest.main()
