# Harder Benchmark: Job Board

Implement a small job board service using only the Python standard library.

Requirements:

- `JobStore(path)` uses SQLite and creates or migrates the schema automatically.
- `create_job(title, company, description, tags=None, remote=False)` validates non-empty text fields, normalizes tags, and returns a job dict.
- `get_job(job_id)`, `list_jobs(status=None, tag=None, remote=None)`, `search_jobs(query)`, `update_job(job_id, **fields)`, and `transition_job(job_id, status)` work against persisted data.
- Valid statuses are `draft`, `open`, `closed`, and `archived`. New jobs default to `draft`.
- Allowed transitions are `draft -> open`, `open -> closed`, `closed -> archived`, and `open -> archived`.
- `export_jobs()` returns a JSON string with all jobs.
- `import_jobs(payload)` validates JSON, imports valid jobs, preserves status/tags/remote, and returns the import count.
- `create_app(store)` returns an HTTP server on `127.0.0.1:0` with JSON routes for health, creating jobs, listing/filtering jobs, searching, transitioning, and exporting.

Verify with:

```sh
python3 -m unittest discover -s tests -v
```
