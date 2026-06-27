import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

from notes import NoteStore, create_app


class NoteStoreTests(unittest.TestCase):
    def make_store(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        return NoteStore(Path(directory.name) / "notes.sqlite")

    def test_crud_search_and_persistence(self):
        store = self.make_store()
        note = store.create_note(" First ", "Body text", tags=["Work", " work ", "api"])

        self.assertEqual(note["id"], 1)
        self.assertEqual(note["title"], "First")
        self.assertEqual(note["tags"], ["api", "work"])
        self.assertEqual(store.get_note(1)["body"], "Body text")
        self.assertEqual([item["id"] for item in store.list_notes(tag="WORK")], [1])
        self.assertEqual([item["id"] for item in store.search_notes("body")], [1])

        updated = store.update_note(1, title="Updated", tags=["docs"])
        self.assertEqual(updated["title"], "Updated")
        self.assertEqual(updated["tags"], ["docs"])
        self.assertTrue(store.delete_note(1))
        self.assertIsNone(store.get_note(1))

    def test_validation_and_import_export(self):
        store = self.make_store()

        with self.assertRaises(ValueError):
            store.create_note("", "body")
        with self.assertRaises(ValueError):
            store.create_note("title", "")
        with self.assertRaises(ValueError):
            store.import_notes("not-json")

        store.create_note("One", "Alpha", tags=["a"])
        payload = store.export_notes()
        data = json.loads(payload)
        self.assertEqual(data["notes"][0]["title"], "One")

        other = self.make_store()
        imported = other.import_notes(payload)
        self.assertEqual(imported, 1)
        self.assertEqual(other.list_notes()[0]["tags"], ["a"])


class NoteHttpTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.store = NoteStore(Path(self.directory.name) / "notes.sqlite")
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
            "/notes",
            {"title": "HTTP", "body": "Searchable body", "tags": ["API"]},
        )
        self.assertEqual(status, 201)
        self.assertEqual(created["id"], 1)

        status, listed = self.request("GET", "/notes?tag=api")
        self.assertEqual(status, 200)
        self.assertEqual([item["title"] for item in listed["notes"]], ["HTTP"])

        status, searched = self.request("GET", "/search?q=searchable")
        self.assertEqual(status, 200)
        self.assertEqual([item["id"] for item in searched["notes"]], [1])

        status, exported = self.request("GET", "/export")
        self.assertEqual(status, 200)
        self.assertEqual(exported["notes"][0]["title"], "HTTP")

        status, error = self.request("GET", "/missing")
        self.assertEqual((status, error), (404, {"error": "not found"}))


if __name__ == "__main__":
    unittest.main()
