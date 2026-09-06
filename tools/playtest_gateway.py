#!/usr/bin/env python3
"""Loopback HTTP allowlist for sharing one SpacetimeDB game through a dev tunnel."""

from __future__ import annotations

import argparse
import asyncio
import base64
import binascii
import contextlib
import hashlib
import ipaddress
import json
import os
import re
import signal
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

HEADER_LIMIT = 32 * 1024
BODY_LIMIT = 64 * 1024
CHUNK_SIZE = 64 * 1024
HEADER_TIMEOUT = 5.0
WRITE_TIMEOUT = 30.0
EOF_TIMEOUT = 3.0
MAX_CONNECTIONS = 128
WEBSOCKET_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
HEADER_NAME = re.compile(r"^[!#$%&'*+.^_`|~0-9a-z-]+$")


class HttpError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class Configuration:
    database: str
    upstream_host: str = "127.0.0.1"
    upstream_port: int = 3210
    listen_port: int = 3211
    ready_file: Path | None = None

    @property
    def websocket_path(self) -> str:
        return f"/v1/database/{self.database}/subscribe"


async def read_head(reader: asyncio.StreamReader) -> tuple[str, dict[str, str]]:
    try:
        raw = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), HEADER_TIMEOUT)
    except TimeoutError as error:
        raise HttpError(408, "HTTP handshake timed out") from error
    except (asyncio.LimitOverrunError, ValueError) as error:
        raise HttpError(431, "HTTP headers are too large") from error
    except asyncio.IncompleteReadError as error:
        raise HttpError(400, "Incomplete HTTP headers") from error
    if len(raw) > HEADER_LIMIT:
        raise HttpError(431, "HTTP headers are too large")
    lines = raw[:-4].decode("latin-1").split("\r\n")
    if not lines or len(lines) > 101:
        raise HttpError(400, "Invalid HTTP headers")
    headers: dict[str, str] = {}
    for line in lines[1:]:
        name, separator, value = line.partition(":")
        name = name.lower()
        if not separator or not HEADER_NAME.fullmatch(name) or name in headers:
            raise HttpError(400, "Invalid or duplicate HTTP header")
        value = value.strip(" \t")
        if any(ord(character) < 32 and character != "\t" for character in value) or "\x7f" in value:
            raise HttpError(400, "Invalid HTTP header value")
        headers[name] = value
    return lines[0], headers


def classify_request(line: str, headers: dict[str, str], config: Configuration) -> tuple[str, str]:
    parts = line.split(" ")
    if len(parts) != 3 or parts[2] != "HTTP/1.1" or not headers.get("host"):
        raise HttpError(400, "Expected an HTTP/1.1 request")
    method, target, _version = parts
    if not target.startswith("/") or "#" in target or any(ord(c) < 33 for c in target):
        raise HttpError(400, "Invalid request target")
    if method == "POST" and target == "/v1/identity" and "transfer-encoding" in headers:
        if headers["transfer-encoding"].lower() != "chunked" or "content-length" in headers:
            raise HttpError(400, "Invalid identity request framing")
        return "identity_chunked", target
    if "transfer-encoding" in headers or headers.get("content-length", "0") != "0":
        raise HttpError(400, "Request bodies are not accepted")
    if method == "GET" and target == "/health":
        return "health", target
    if method == "POST" and target == "/v1/identity":
        return "identity", target
    path, _, query = target.partition("?")
    if method != "GET" or path != config.websocket_path:
        raise HttpError(403, "Route is not exposed by this game gateway")
    if headers.get("upgrade", "").lower() != "websocket":
        raise HttpError(400, "A WebSocket upgrade is required")
    if "upgrade" not in {part.strip().lower() for part in headers.get("connection", "").split(",")}:
        raise HttpError(400, "A WebSocket connection upgrade is required")
    if headers.get("sec-websocket-version") != "13":
        raise HttpError(400, "WebSocket version 13 is required")
    try:
        key = base64.b64decode(headers.get("sec-websocket-key", ""), validate=True)
    except (ValueError, binascii.Error) as error:
        raise HttpError(400, "Invalid WebSocket key") from error
    if len(key) != 16:
        raise HttpError(400, "Invalid WebSocket key")
    if headers.get("sec-websocket-protocol") != "v3.bsatn.spacetimedb":
        raise HttpError(400, "The game's v3 SpacetimeDB protocol is required")
    try:
        parameters = parse_qsl(query, strict_parsing=True, max_num_fields=8)
    except ValueError as error:
        raise HttpError(400, "Invalid WebSocket query") from error
    names = [name for name, _value in parameters]
    if len(names) != len(set(names)) or set(names) - {
        "connection_id",
        "compression",
        "confirmed",
        "token",
    }:
        raise HttpError(400, "Unsupported WebSocket query")
    values = dict(parameters)
    if "connection_id" in values and not re.fullmatch(r"[a-fA-F0-9]{32}", values["connection_id"]):
        raise HttpError(400, "Invalid connection identifier")
    if values.get("compression", "None") not in {"None", "Gzip"}:
        raise HttpError(400, "Unsupported compression")
    if values.get("confirmed", "false") not in {"true", "false"}:
        raise HttpError(400, "Invalid confirmation preference")
    return "websocket", target


async def read_empty_identity_body(reader: asyncio.StreamReader) -> None:
    # Cloudflare can frame its empty origin POST as chunked. Accept only a bare
    # terminating zero chunk, with no data, extensions, or trailers. The upstream
    # always receives our freshly constructed Content-Length: 0 request.
    try:
        body = await asyncio.wait_for(reader.readexactly(5), HEADER_TIMEOUT)
    except TimeoutError as error:
        raise HttpError(408, "Identity request body timed out") from error
    except asyncio.IncompleteReadError as error:
        raise HttpError(400, "Incomplete identity request body") from error
    if body != b"0\r\n\r\n":
        raise HttpError(400, "Identity bootstrap requires an empty body without trailers")


async def send_response(
    writer: asyncio.StreamWriter, status: int, body: bytes, content_type: str = "application/json"
) -> None:
    headers = (
        f"HTTP/1.1 {status} Gateway Response\r\nContent-Type: {content_type}\r\n"
        f"Content-Length: {len(body)}\r\nCache-Control: no-store\r\nConnection: close\r\n\r\n"
    )
    writer.write(headers.encode("latin-1") + body)
    await asyncio.wait_for(writer.drain(), WRITE_TIMEOUT)


async def bounded_body(reader: asyncio.StreamReader, headers: dict[str, str]) -> bytes:
    async with asyncio.timeout(HEADER_TIMEOUT):
        if "transfer-encoding" in headers:
            if headers["transfer-encoding"].lower() != "chunked" or "content-length" in headers:
                raise HttpError(502, "Unsupported upstream response framing")
            body = bytearray()
            while True:
                size_line = await reader.readuntil(b"\r\n")
                if len(size_line) > 128:
                    raise HttpError(502, "Invalid upstream response")
                try:
                    size = int(size_line.split(b";", 1)[0].strip(), 16)
                except ValueError as error:
                    raise HttpError(502, "Invalid upstream response") from error
                if size < 0 or size + len(body) > BODY_LIMIT:
                    raise HttpError(502, "Upstream response is too large")
                if size == 0:
                    trailers = 0
                    while True:
                        trailer = await reader.readuntil(b"\r\n")
                        trailers += len(trailer)
                        if trailers > HEADER_LIMIT:
                            raise HttpError(502, "Upstream trailers are too large")
                        if trailer == b"\r\n":
                            return bytes(body)
                body.extend(await reader.readexactly(size))
                if await reader.readexactly(2) != b"\r\n":
                    raise HttpError(502, "Invalid upstream response")
        if "content-length" in headers:
            try:
                size = int(headers["content-length"])
            except ValueError as error:
                raise HttpError(502, "Invalid upstream response length") from error
            if not 0 <= size <= BODY_LIMIT:
                raise HttpError(502, "Upstream response is too large")
            return await reader.readexactly(size)
        body = bytearray()
        while data := await reader.read(CHUNK_SIZE):
            body.extend(data)
            if len(body) > BODY_LIMIT:
                raise HttpError(502, "Upstream response is too large")
        return bytes(body)


async def pump(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    while data := await reader.read(CHUNK_SIZE):
        writer.write(data)
        await asyncio.wait_for(writer.drain(), WRITE_TIMEOUT)
    if writer.can_write_eof():
        writer.write_eof()
        await asyncio.wait_for(writer.drain(), WRITE_TIMEOUT)


async def relay(
    left_reader: asyncio.StreamReader,
    left_writer: asyncio.StreamWriter,
    right_reader: asyncio.StreamReader,
    right_writer: asyncio.StreamWriter,
) -> None:
    tasks = {
        asyncio.create_task(pump(left_reader, right_writer)),
        asyncio.create_task(pump(right_reader, left_writer)),
    }
    try:
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            task.result()
        if pending:
            await asyncio.wait_for(asyncio.gather(*pending), EOF_TIMEOUT)
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


class Gateway:
    def __init__(self, config: Configuration):
        self.config = config
        self.server: asyncio.Server | None = None
        self.handlers: set[asyncio.Task] = set()

    async def start(self) -> int:
        self.server = await asyncio.start_server(
            self.handle, "127.0.0.1", self.config.listen_port, limit=HEADER_LIMIT
        )
        return self.server.sockets[0].getsockname()[1]

    async def close(self) -> None:
        if self.server:
            self.server.close()
        for task in tuple(self.handlers):
            task.cancel()
        await asyncio.gather(*tuple(self.handlers), return_exceptions=True)
        if self.server:
            await self.server.wait_closed()

    async def open_upstream(self) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        return await asyncio.wait_for(
            asyncio.open_connection(
                self.config.upstream_host, self.config.upstream_port, limit=HEADER_LIMIT
            ),
            HEADER_TIMEOUT,
        )

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        task = asyncio.current_task()
        upstream_writer = None
        upgraded = False
        try:
            if len(self.handlers) >= MAX_CONNECTIONS:
                raise HttpError(503, "Gateway connection capacity reached")
            self.handlers.add(task)
            writer.transport.set_write_buffer_limits(high=CHUNK_SIZE, low=CHUNK_SIZE // 4)
            line, headers = await read_head(reader)
            kind, target = classify_request(line, headers, self.config)
            if kind == "identity_chunked":
                await read_empty_identity_body(reader)
                kind = "identity"
            if kind == "health":
                reachable = False
                try:
                    _upstream_reader, upstream_writer = await self.open_upstream()
                    reachable = True
                except (OSError, TimeoutError):
                    pass
                body = json.dumps(
                    {"database": self.config.database, "upstream_reachable": reachable}
                ).encode()
                await send_response(writer, 200 if reachable else 503, body)
                return
            upstream_reader, upstream_writer = await self.open_upstream()
            upstream_writer.transport.set_write_buffer_limits(high=CHUNK_SIZE, low=CHUNK_SIZE // 4)
            host = self.config.upstream_host
            if ":" in host:
                host = f"[{host}]"
            request = [
                f"{'POST' if kind == 'identity' else 'GET'} {target} HTTP/1.1",
                f"Host: {host}:{self.config.upstream_port}",
            ]
            if kind == "identity":
                request.extend(["Content-Length: 0", "Connection: close"])
            else:
                request.extend(["Upgrade: websocket", "Connection: Upgrade"])
                for name in (
                    "sec-websocket-key",
                    "sec-websocket-version",
                    "sec-websocket-protocol",
                    "authorization",
                    "origin",
                ):
                    if name in headers:
                        request.append(f"{name}: {headers[name]}")
            upstream_writer.write(("\r\n".join(request) + "\r\n\r\n").encode("latin-1"))
            await asyncio.wait_for(upstream_writer.drain(), WRITE_TIMEOUT)
            status_line, response_headers = await read_head(upstream_reader)
            match = re.fullmatch(r"HTTP/1\.[01] ([1-5][0-9]{2})(?: .*)?", status_line)
            if not match:
                raise HttpError(502, "Invalid upstream status")
            status = int(match[1])
            if kind == "identity" or status != 101:
                if status == 101:
                    raise HttpError(502, "Unexpected upstream upgrade")
                body = await bounded_body(upstream_reader, response_headers)
                await send_response(
                    writer, status, body, response_headers.get("content-type", "application/json")
                )
                return
            accept = base64.b64encode(
                hashlib.sha1((headers["sec-websocket-key"] + WEBSOCKET_GUID).encode()).digest()
            ).decode()
            if (
                response_headers.get("upgrade", "").lower() != "websocket"
                or "upgrade"
                not in {
                    part.strip().lower()
                    for part in response_headers.get("connection", "").split(",")
                }
                or response_headers.get("sec-websocket-accept") != accept
                or response_headers.get("sec-websocket-protocol") != "v3.bsatn.spacetimedb"
            ):
                raise HttpError(502, "Invalid upstream WebSocket upgrade")
            response = [
                status_line,
                *(f"{key}: {value}" for key, value in response_headers.items()),
            ]
            writer.write(("\r\n".join(response) + "\r\n\r\n").encode("latin-1"))
            await asyncio.wait_for(writer.drain(), WRITE_TIMEOUT)
            upgraded = True
            await relay(reader, writer, upstream_reader, upstream_writer)
        except HttpError as error:
            if not upgraded:
                with contextlib.suppress(ConnectionError, TimeoutError):
                    await send_response(
                        writer, error.status, json.dumps({"error": str(error)}).encode()
                    )
        except (OSError, TimeoutError, asyncio.IncompleteReadError, asyncio.LimitOverrunError):
            if not upgraded:
                with contextlib.suppress(ConnectionError, TimeoutError):
                    await send_response(writer, 502, b'{"error":"Upstream connection failed"}')
        finally:
            for stream in (upstream_writer, writer):
                if stream:
                    stream.close()
                    try:
                        await asyncio.wait_for(stream.wait_closed(), 1.0)
                    except (OSError, TimeoutError):
                        stream.transport.abort()
            self.handlers.discard(task)


async def serve(config: Configuration) -> None:
    gateway = Gateway(config)
    port = await gateway.start()
    stopped = asyncio.Event()
    loop = asyncio.get_running_loop()
    for name in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(name, stopped.set)
    ready = {
        "pid": os.getpid(),
        "database": config.database,
        "url": f"http://127.0.0.1:{port}",
        "upstream": f"http://{config.upstream_host}:{config.upstream_port}",
        "started_at": int(time.time()),
    }
    try:
        if config.ready_file:
            config.ready_file.parent.mkdir(parents=True, exist_ok=True)
            temporary = config.ready_file.with_suffix(".tmp")
            temporary.write_text(json.dumps(ready, indent=2) + "\n")
            temporary.replace(config.ready_file)
        print(json.dumps({"gateway_ready": ready}), flush=True)
        await stopped.wait()
    finally:
        await gateway.close()
        if config.ready_file:
            with contextlib.suppress(OSError, ValueError):
                if json.loads(config.ready_file.read_text()).get("pid") == os.getpid():
                    config.ready_file.unlink()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default="mt2-dev-world")
    parser.add_argument("--upstream", default="http://127.0.0.1:3210")
    parser.add_argument("--listen-port", type=int, default=3211)
    parser.add_argument("--ready-file", type=Path)
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9_-]+", args.database):
        parser.error(
            "database must contain only lowercase letters, digits, underscores, or hyphens"
        )
    upstream = urlsplit(args.upstream)
    try:
        loopback = (
            upstream.hostname == "localhost"
            or ipaddress.ip_address(upstream.hostname or "").is_loopback
        )
        port = upstream.port or 80
    except ValueError:
        parser.error("upstream must be a valid loopback HTTP address")
    if (
        upstream.scheme != "http"
        or not loopback
        or upstream.username
        or upstream.password
        or upstream.path not in {"", "/"}
        or upstream.query
        or upstream.fragment
    ):
        parser.error("upstream must be a loopback HTTP origin without credentials or a path")
    if not 0 <= args.listen_port <= 65535:
        parser.error("listen-port must be between 0 and 65535")
    try:
        asyncio.run(
            serve(
                Configuration(
                    args.database, upstream.hostname, port, args.listen_port, args.ready_file
                )
            )
        )
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
