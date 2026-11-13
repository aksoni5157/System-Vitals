"""Offline generative chat adapter backed by a local Ollama instance."""

import json
import logging
import threading
import time
from http.client import HTTPConnection, HTTPException
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

logger = logging.getLogger("SisVi+.VitaChat")


class HybridChatEngine:
    """Use Qwen through Ollama's local API for generative chat."""

    is_online = False
    model = "qwen3:0.6b"
    api_url = "http://localhost:11434"
    health_cache_seconds = 600.0

    def __init__(self):
        self._history = []
        self._health_lock = threading.Lock()
        self._health_cache = None
        self._health_checked_at = 0.0
        self._connection_lock = threading.Lock()
        self._api_connection = None

    def check_model(self, force=False):
        """Check local Ollama readiness, caching successful checks briefly."""
        now = time.monotonic()
        with self._health_lock:
            if (not force and self._health_cache is not None):
                age = now - self._health_checked_at
                ready = self._health_cache[0]
                # Don't leave the UI stuck on an old offline result after Ollama starts.
                cache_ttl = self.health_cache_seconds if ready else 5.0
                if age < cache_ttl:
                    return self._health_cache
            request = Request(self.api_url + "/api/tags",
                              headers={"Accept": "application/json"})
            try:
                with urlopen(request, timeout=5.0) as response:
                    tags = json.loads(response.read().decode("utf-8"))
            except (URLError, TimeoutError, OSError) as exc:
                result = (False, f"Ollama is not running ({exc}).")
            except HTTPError as exc:
                result = (False, f"Ollama API returned HTTP {exc.code}.")
            except ValueError as exc:
                result = (False, f"Ollama returned invalid model-list data ({exc}).")
            else:
                names = {item.get("name", "") for item in tags.get("models", [])}
                if self.model not in names and self.model + ":latest" not in names:
                    result = (False, f"Model {self.model} is not downloaded.")
                else:
                    result = (True, "Local model ready.")
            self._health_cache = result
            self._health_checked_at = time.monotonic()
            return result

    def stream_response(self, query, snapshot=None, diagnosis=None, on_chunk=None,
                        submitted_at=None, submitted_monotonic=None):
        """Stream a local response and retain a short multi-turn conversation."""
        snapshot = snapshot or {}
        messages = [{"role": "system", "content": self._system_prompt(snapshot, diagnosis)}]
        messages.extend(self._history[-8:])
        messages.append({"role": "user", "content": str(query)})
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "think": False,
            "keep_alive": "30m",
            "options": {
                "num_ctx": 4096,
                "num_predict": 384,
                "temperature": 0.65,
                "top_p": 0.9,
            },
        }
        request = Request(
            self.api_url + "/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/x-ndjson"},
            method="POST",
        )
        answer = []
        request_started = time.perf_counter()
        response_headers_at = None
        first_token_at = None
        ollama_stats = {}
        try:
            endpoint = urlsplit(self.api_url)
            path = (endpoint.path.rstrip("/") + "/api/chat") or "/api/chat"
            port = endpoint.port or 80
            with self._connection_lock:
                if self._api_connection is None:
                    self._api_connection = HTTPConnection(
                        endpoint.hostname, port, timeout=300)
                connection = self._api_connection
                try:
                    connection.request(
                        "POST", path, body=request.data,
                        headers={"Content-Type": "application/json",
                                 "Accept": "application/x-ndjson"})
                    response = connection.getresponse()
                    response_headers_at = time.perf_counter()
                    if response.status >= 400:
                        detail = response.read().decode("utf-8", errors="replace")
                        raise RuntimeError(
                            f"Local model request failed: HTTP {response.status}: {detail}")
                    for raw_line in response:
                        if not raw_line.strip():
                            continue
                        item = json.loads(raw_line.decode("utf-8"))
                        if item.get("error"):
                            raise RuntimeError(item["error"])
                        piece = item.get("message", {}).get("content", "")
                        if piece:
                            if first_token_at is None:
                                first_token_at = time.perf_counter()
                            answer.append(piece)
                            if on_chunk:
                                on_chunk(piece)
                        if item.get("done"):
                            ollama_stats = {
                                key: item.get(key) for key in (
                                    "total_duration", "load_duration",
                                    "prompt_eval_duration", "eval_duration",
                                    "prompt_eval_count", "eval_count")
                                if item.get(key) is not None
                            }
                except (HTTPException, OSError, ValueError):
                    connection.close()
                    self._api_connection = None
                    raise
        except (HTTPError, URLError, TimeoutError, OSError,
                HTTPException, ValueError) as exc:
            self._log_timing(submitted_at, submitted_monotonic, request_started,
                             response_headers_at, first_token_at, None, {})
            raise RuntimeError(f"Local model request failed: {exc}") from exc
        finished_at = time.perf_counter()
        self._log_timing(submitted_at, submitted_monotonic, request_started,
                         response_headers_at, first_token_at, finished_at, ollama_stats)
        result = "".join(answer).strip()
        if not result:
            raise RuntimeError("The local model returned an empty response.")
        self._history.extend((
            {"role": "user", "content": str(query)},
            {"role": "assistant", "content": result},
        ))
        self._history = self._history[-8:]
        return result

    @staticmethod
    def _log_timing(submitted_at, submitted_monotonic, request_started,
                    headers_at, first_token_at, finished_at, stats):
        ms = lambda value: round(value * 1000) if value is not None else None
        submit_to_first = (ms(first_token_at - submitted_monotonic)
                           if first_token_at is not None and submitted_monotonic is not None
                           else None)
        logger.info(
            "VITA timing submit_at=%s request_start_delay_ms=%s "
            "api_headers_ms=%s first_token_ms=%s submit_to_first_token_ms=%s "
            "total_ms=%s ollama_load_ms=%s prompt_eval_ms=%s generation_ms=%s "
            "prompt_tokens=%s generated_tokens=%s",
            submitted_at or "unknown",
            ms(request_started - submitted_monotonic)
                if submitted_monotonic is not None else None,
            ms(headers_at - request_started) if headers_at is not None else None,
            ms(first_token_at - request_started) if first_token_at is not None else None,
            submit_to_first,
            ms(finished_at - submitted_monotonic)
                if finished_at is not None and submitted_monotonic is not None
                else ms(finished_at - request_started) if finished_at is not None else None,
            round(stats["load_duration"] / 1000000) if "load_duration" in stats else None,
            round(stats["prompt_eval_duration"] / 1000000)
                if "prompt_eval_duration" in stats else None,
            round(stats["eval_duration"] / 1000000) if "eval_duration" in stats else None,
            stats.get("prompt_eval_count"), stats.get("eval_count"),
        )

    @staticmethod
    def _system_prompt(snapshot, diagnosis):
        metrics = []
        for key, label in (("cpu_load", "CPU"), ("ram_usage", "RAM"),
                           ("storage_health", "Storage"), ("battery_soh", "Battery"),
                           ("session_mins", "Session minutes")):
            value = snapshot.get(key)
            if isinstance(value, (int, float)):
                metrics.append(f"{label}: {value:.0f}")
        score = getattr(diagnosis, "balance_score", None)
        severity = getattr(diagnosis, "severity", None)
        if isinstance(score, (int, float)):
            metrics.append(f"Life Balance score: {score:.0f} ({severity or 'unknown'})")
        context = "; ".join(metrics) if metrics else "No live system readings are available."
        return (
            "You are Vita AI, the friendly offline assistant in the System Vitals desktop app. "
            "Answer naturally and accurately. Use the supplied live readings when relevant, "
            "and say when information is unavailable. Do not claim internet access. "
            f"Current system context: {context}"
        )

    def respond(self, query, snapshot=None, diagnosis=None):
        """Compatibility method for callers that need a complete response."""
        if isinstance(query, dict):
            diagnosis, snapshot, query = snapshot, query, "overview"
        return self.stream_response(query, snapshot, diagnosis)
