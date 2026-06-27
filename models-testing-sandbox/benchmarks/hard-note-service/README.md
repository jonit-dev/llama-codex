# Hard Benchmark: Note Service

Implement a small note service using only the Python standard library.

Requirements:

- `NoteStore(path)` uses SQLite and creates or migrates the schema automatically.
- `create_note(title, body, tags=None)` validates non-empty title/body, normalizes tags, and returns a note dict.
- `get_note(note_id)`, `list_notes(tag=None)`, `search_notes(query)`, `update_note(note_id, **fields)`, and `delete_note(note_id)` work against persisted data.
- `export_notes()` returns a JSON string with all notes.
- `import_notes(payload)` validates JSON, imports notes, and preserves tags.
- `create_app(store)` returns an HTTP server on `127.0.0.1:0` with JSON routes for creating, listing, searching, exporting, and health.

Verify with:

```sh
python3 -m unittest discover -s tests -v
```
