# Local Model Testing Sandbox

This folder contains repeatable coding benchmarks for local model tests.

Copy a benchmark fixture into `runs/<model-name>-<tier>/` before each attempt so every model starts from the same state.

Available tiers:

- `base/`: easy compatibility fixture kept for earlier results.
- `benchmarks/easy-api/`: easy single-file HTTP API.
- `benchmarks/medium-task-library/`: medium multi-file task library with validation, filtering, and JSON persistence.
- `benchmarks/hard-note-service/`: hard small service with SQLite persistence, migration, search, import/export, and HTTP routes.

Run the verification command from a copied fixture unless a fixture README says otherwise:

```sh
python3 -m unittest discover -s tests -v
```

Expected API behavior:

- `GET /health` returns `200` with `{"status":"ok"}`.
- `POST /items` with `{"name":"alpha"}` returns `201` with `{"id":1,"name":"alpha"}`.
- `GET /items` returns `200` with the created items.
- `POST /items` with a missing or empty name returns `400` with `{"error":"name is required"}`.
- Unknown routes return `404` with `{"error":"not found"}`.
