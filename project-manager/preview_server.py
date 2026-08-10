"""Small local preview server that prevents stale portfolio assets."""

from __future__ import annotations

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class NoCachePreviewHandler(SimpleHTTPRequestHandler):
    """Serve repository files while forcing browsers to request fresh copies."""

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve a portfolio preview without browser caching.")
    parser.add_argument("port", type=int)
    parser.add_argument("repository", type=Path)
    arguments = parser.parse_args()

    repository = arguments.repository.resolve()
    handler = partial(NoCachePreviewHandler, directory=str(repository))
    server = ThreadingHTTPServer(("127.0.0.1", arguments.port), handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
