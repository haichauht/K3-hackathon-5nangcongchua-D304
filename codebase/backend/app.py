"""Application lifecycle for VLearn Recall."""

from __future__ import annotations

from http.server import ThreadingHTTPServer

from backend.api.router import VLearnRequestHandler
from backend.capabilities import health_status
from backend.config import SETTINGS, Settings
from backend.rag.retriever import ensure_runtime_index


class VLearnApplication:
    """Owns startup, HTTP serving and graceful shutdown."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.httpd: ThreadingHTTPServer | None = None

    def warmup(self) -> None:
        ensure_runtime_index()

    def run(self) -> None:
        self.warmup()
        self.httpd = ThreadingHTTPServer(
            (self.settings.host, self.settings.port),
            VLearnRequestHandler,
        )
        status = health_status()
        retrieval = status["data"]["retrieval"]
        print(
            "VLearn Recall listening on "
            f"http://{self.settings.host}:{self.settings.port} "
            f"(answer_mode={status['ai_mode']}, rag_index={retrieval['index_mode']})"
        )
        try:
            self.httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nStopping VLearn Recall.")
        finally:
            self.shutdown()

    def shutdown(self) -> None:
        if self.httpd is not None:
            self.httpd.server_close()
            self.httpd = None


def create_app(settings: Settings | None = None) -> VLearnApplication:
    return VLearnApplication(settings or SETTINGS)


__all__ = ["VLearnApplication", "create_app"]
