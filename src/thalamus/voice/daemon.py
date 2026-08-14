"""Resident speech synthesiser for the console's tap-to-listen control.

Runs as its own service rather than inside the console for two reasons. The
console is stdlib-only and restarts itself on edit; torch and a GPU-resident
model have no business in a process with that lifecycle. And the model's cost
is almost entirely load, not synthesis — measured at roughly 1.5s of a 2s
cold invocation — so the only architecture that pays for itself keeps one
pipeline warm and answers requests against it.

The GPU matters here less for speed than for contention. This box has four
cores and already runs the roster, the console, pulse, ttyd and a media stack
on them; a CUDA-resident pipeline does its work on none of them. torch is
still pinned to a single thread, because it otherwise helps itself to all four
during the parts that do run on CPU.

This module is deliberately importable with nothing from `thalamus` on the
path: it runs under its own venv outside the checkout, holding the heavy
dependencies away from the package while the code stays versioned with it.

Synthesis is serialized behind a lock. One pipeline is not concurrency-safe,
and the surface it serves speaks one session at a time by design, so a queue
of one is the whole requirement.
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import threading
import time
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

LOG = logging.getLogger("thalamus.voice")

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8380
DEFAULT_VOICE = "af_heart"
DEFAULT_LANG = "a"
SAMPLE_RATE = 24_000

# Long enough for a substantial update, short enough that a runaway request
# cannot pin the GPU. Speech runs ~13 characters/second, so this is ~5 minutes.
MAX_CHARS = 4000


class Synthesiser:
    """One warm pipeline, and the lock that keeps it to one caller at a time."""

    def __init__(self, voice: str = DEFAULT_VOICE, lang: str = DEFAULT_LANG,
                 device: str = "cuda") -> None:
        self.voice = voice
        self.lang = lang
        self.device = device
        self._lock = threading.Lock()
        self._pipeline = None
        self._loaded_at = 0.0

    def warm(self) -> None:
        """Load the model now, so the first tap is not the one that pays for it.

        Synthesising a throwaway word is part of warming, not a smoke test: the
        voice tensor is fetched lazily on first use, separately from the model,
        so a pipeline that has only been constructed still owes a network round
        trip — and would fail outright on a box that is offline when the first
        tap arrives.

        Constructing the pipeline is inside the guard, not outside it: `kokoro` and
        `torch` are installed by hand into a venv this package does not describe, so
        a missing one is an ordinary deployment state rather than a bug. Warming is
        an optimisation, and an optimisation that refuses to start the service it is
        meant to speed up has the failure backwards — the daemon comes up, /health
        answers, and the first request pays the cost or reports the real error.
        """
        with self._lock:
            try:
                pipeline = self._ensure_pipeline()
                for _ in pipeline("ready", voice=self.voice):
                    break
            except Exception:
                LOG.exception("voice pre-load failed; first request will be slower")

    def _ensure_pipeline(self):
        if self._pipeline is not None:
            return self._pipeline
        import torch
        from kokoro import KPipeline

        # torch takes every core it can find; on a four-core box shared with the
        # roster and the media stack that is the difference between a background
        # service and a foreground one.
        torch.set_num_threads(1)

        device = self.device
        if device == "cuda" and not torch.cuda.is_available():
            LOG.warning("cuda requested but unavailable — falling back to cpu")
            device = "cpu"

        started = time.monotonic()
        self._pipeline = KPipeline(lang_code=self.lang, device=device,
                                   repo_id="hexgrad/Kokoro-82M")
        self._loaded_at = time.monotonic() - started
        LOG.info("pipeline warm on %s in %.2fs", device, self._loaded_at)
        return self._pipeline

    def to_wav(self, text: str, voice: str = "", speed: float = 1.0) -> bytes:
        """Synthesise one utterance and return a complete RIFF wav."""
        import numpy as np

        with self._lock:
            pipeline = self._ensure_pipeline()
            started = time.monotonic()
            chunks = [audio for _, _, audio in
                      pipeline(text, voice=voice or self.voice, speed=speed)]
            elapsed = time.monotonic() - started

        if not chunks:
            raise ValueError("synthesis produced no audio")

        samples = np.concatenate(chunks)
        LOG.info("spoke %.2fs of audio in %.2fs (rtf %.3f)",
                 len(samples) / SAMPLE_RATE, elapsed,
                 elapsed / max(len(samples) / SAMPLE_RATE, 1e-6))
        return encode_wav(samples)


def encode_wav(samples) -> bytes:
    """Float samples in [-1, 1] to 16-bit PCM in a wav container."""
    import numpy as np

    clipped = np.clip(np.asarray(samples, dtype="float32"), -1.0, 1.0)
    pcm = (clipped * 32767.0).astype("<i2")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(SAMPLE_RATE)
        out.writeframes(pcm.tobytes())
    return buffer.getvalue()


class Handler(BaseHTTPRequestHandler):
    synthesiser: Synthesiser = None  # set on the server before serving

    protocol_version = "HTTP/1.1"
    server_version = "thalamus-voice"

    def log_message(self, fmt, *args):  # noqa: A003 - BaseHTTPRequestHandler API
        LOG.debug(fmt, *args)

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        # The console proxies this to a phone; a stale utterance is worse than
        # no utterance, and the audio is cheap to regenerate.
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _fail(self, code: int, reason: str) -> None:
        self._send(code, json.dumps({"ok": False, "error": reason}).encode(),
                   "application/json")

    def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler API
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            ready = self.synthesiser._pipeline is not None
            self._send(200, json.dumps({"ok": True, "warm": ready}).encode(),
                       "application/json")
            return
        if parsed.path != "/say":
            self._fail(404, "no such path")
            return

        params = parse_qs(parsed.query)
        text = (params.get("text") or [""])[0].strip()
        if not text:
            self._fail(400, "no text")
            return
        if len(text) > MAX_CHARS:
            self._fail(413, f"text over {MAX_CHARS} characters")
            return

        voice = (params.get("voice") or [""])[0].strip()
        try:
            speed = float((params.get("speed") or ["1.0"])[0])
        except ValueError:
            speed = 1.0
        speed = min(max(speed, 0.5), 2.0)

        try:
            audio = self.synthesiser.to_wav(text, voice=voice, speed=speed)
        except Exception as exc:  # a synthesis failure must not kill the service
            LOG.exception("synthesis failed")
            self._fail(500, str(exc))
            return
        self._send(200, audio, "audio/wav")


def serve(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT,
          voice: str = DEFAULT_VOICE, device: str = "cuda",
          warm: bool = True) -> None:
    synthesiser = Synthesiser(voice=voice, device=device)
    if warm:
        synthesiser.warm()

    handler = type("BoundHandler", (Handler,), {"synthesiser": synthesiser})
    server = ThreadingHTTPServer((host, port), handler)
    LOG.info("listening on %s:%d", host, port)
    server.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--voice", default=DEFAULT_VOICE)
    parser.add_argument("--device", default="cuda", choices=["cuda", "cpu"])
    parser.add_argument("--no-warm", action="store_true",
                        help="defer model load until the first request")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    serve(host=args.host, port=args.port, voice=args.voice,
          device=args.device, warm=not args.no_warm)


if __name__ == "__main__":
    main()
