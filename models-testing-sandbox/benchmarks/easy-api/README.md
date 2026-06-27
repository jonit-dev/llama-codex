# Easy Benchmark: Tiny API

Implement `create_app()` in `api.py` using only the Python standard library.

The tests expect `create_app()` to return a configured HTTP server bound to `("127.0.0.1", 0)`. The tests start and stop the server.

Verify with:

```sh
python3 -m unittest discover -s tests -v
```
