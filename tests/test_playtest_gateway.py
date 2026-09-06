"""HTTP allowlist, WebSocket framing, backpressure, and cleanup regression tests."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import playtest_gateway as gateway_module  # noqa: E402

KEY = base64.b64encode(b"0123456789abcdef").decode()
DATABASE = "gateway-test"
PATH = f"/v1/database/{DATABASE}/subscribe"


def handshake(path: str = PATH, extras: str = "") -> bytes:
    return (
        f"GET {path} HTTP/1.1\r\nHost: external.example\r\nUpgrade: websocket\r\n"
        f"Connection: Upgrade\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Key: {KEY}\r\n"
        f"Sec-WebSocket-Protocol: v3.bsatn.spacetimedb\r\n{extras}\r\n"
    ).encode()


def frame(payload: bytes, masked: bool = False, opcode: int = 2) -> bytes:
    mask_flag = 128 if masked else 0
    size = len(payload)
    if size < 126:
        header = bytes([128 | opcode, mask_flag | size])
    elif size < 65536:
        header = bytes([128 | opcode, mask_flag | 126]) + struct.pack("!H", size)
    else:
        header = bytes([128 | opcode, mask_flag | 127]) + struct.pack("!Q", size)
    if not masked:
        return header + payload
    mask = b"mt2!"
    return header + mask + bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))


async def read_frame(reader: asyncio.StreamReader) -> tuple[int, bytes]:
    header = await reader.readexactly(2)
    size = header[1] & 127
    if size == 126:
        size = struct.unpack("!H", await reader.readexactly(2))[0]
    elif size == 127:
        size = struct.unpack("!Q", await reader.readexactly(8))[0]
    mask = await reader.readexactly(4) if header[1] & 128 else b""
    payload = await reader.readexactly(size)
    if mask:
        payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
    return header[0] & 15, payload


class GatewayTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.requests: list[bytes] = []
        self.upstream_tasks: set[asyncio.Task] = set()
        self.read_gate = asyncio.Event()
        self.read_gate.set()
        self.upstream_status = 101
        self.identity_chunked = False
        self.identity_oversized = False
        self.send_on_eof = False
        self.upstream = await asyncio.start_server(self.fake_upstream, "127.0.0.1", 0)
        upstream_port = self.upstream.sockets[0].getsockname()[1]
        self.gateway = gateway_module.Gateway(
            gateway_module.Configuration(DATABASE, upstream_port=upstream_port, listen_port=0)
        )
        self.port = await self.gateway.start()
        self.writers: list[asyncio.StreamWriter] = []

    async def asyncTearDown(self) -> None:
        for writer in self.writers:
            writer.close()
            with contextlib.suppress(OSError):
                await writer.wait_closed()
        await self.gateway.close()
        self.upstream.close()
        await self.upstream.wait_closed()
        for task in tuple(self.upstream_tasks):
            task.cancel()
        await asyncio.gather(*tuple(self.upstream_tasks), return_exceptions=True)

    async def connect(self) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        reader, writer = await asyncio.open_connection("127.0.0.1", self.port)
        self.writers.append(writer)
        return reader, writer

    async def request(self, data: bytes) -> tuple[int, bytes]:
        reader, writer = await self.connect()
        writer.write(data)
        await writer.drain()
        response = await asyncio.wait_for(reader.read(), 2)
        head, _, body = response.partition(b"\r\n\r\n")
        return int(head.split(b" ")[1]), body

    async def fake_upstream(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        task = asyncio.current_task()
        self.upstream_tasks.add(task)
        try:
            request = await reader.readuntil(b"\r\n\r\n")
            self.requests.append(request)
            if request.startswith(b"POST /v1/identity "):
                if self.identity_oversized:
                    writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 1000000\r\n\r\n")
                elif self.identity_chunked:
                    writer.write(
                        b'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\nf\r\n{"token":"abc"}\r\n0\r\n\r\n'
                    )
                else:
                    writer.write(
                        b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 15\r\n\r\n{"token":"abc"}'
                    )
                await writer.drain()
                return
            if self.upstream_status != 101:
                writer.write(
                    f"HTTP/1.1 {self.upstream_status} Rejected\r\nContent-Length: 2\r\n\r\n{{}}".encode()
                )
                await writer.drain()
                return
            accept = base64.b64encode(
                hashlib.sha1((KEY + gateway_module.WEBSOCKET_GUID).encode()).digest()
            ).decode()
            writer.write(
                (
                    f"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: keep-alive, Upgrade\r\n"
                    f"Sec-WebSocket-Accept: {accept}\r\nSec-WebSocket-Protocol: v3.bsatn.spacetimedb\r\n\r\n"
                ).encode()
            )
            await writer.drain()
            await self.read_gate.wait()
            while True:
                try:
                    opcode, payload = await read_frame(reader)
                except asyncio.IncompleteReadError:
                    if self.send_on_eof:
                        writer.write(frame(b"last-message-after-eof"))
                        await writer.drain()
                    return
                writer.write(frame(payload, opcode=opcode))
                await writer.drain()
                if opcode == 8:
                    return
        except (OSError, asyncio.IncompleteReadError):
            pass
        finally:
            writer.close()
            with contextlib.suppress(OSError):
                await writer.wait_closed()
            self.upstream_tasks.discard(task)

    async def test_admin_other_database_and_encoded_routes_never_reach_upstream(self) -> None:
        requests = [
            b"POST /v1/database HTTP/1.1\r\nHost: example\r\n\r\n",
            b"PUT /v1/database/gateway-test HTTP/1.1\r\nHost: example\r\n\r\n",
            b"DELETE /v1/database/gateway-test HTTP/1.1\r\nHost: example\r\n\r\n",
            b"POST /v1/database/gateway-test/sql HTTP/1.1\r\nHost: example\r\n\r\n",
            b"GET /v1/database/gateway-test/logs HTTP/1.1\r\nHost: example\r\n\r\n",
            b"GET /v1/database/gateway-test/schema HTTP/1.1\r\nHost: example\r\n\r\n",
            handshake("/v1/database/other/subscribe"),
            handshake("/v1/database/%67ateway-test/subscribe"),
            handshake("/v1/database/gateway-test/subscribe/../sql"),
            handshake(PATH + "?unsupported=true"),
        ]
        for request in requests:
            with self.subTest(request=request.split(b"\r\n", 1)[0]):
                status, _body = await self.request(request)
                self.assertIn(status, {400, 403})
        self.assertEqual(self.requests, [])

    async def test_request_smuggling_shapes_and_nonupgrades_are_rejected(self) -> None:
        for request in [
            handshake(extras="Host: duplicate\r\n"),
            handshake(extras="Content-Length: 4\r\n") + b"evil",
            handshake(extras="Transfer-Encoding: chunked\r\n"),
            handshake(extras=" folded: value\r\n"),
            f"GET {PATH} HTTP/1.1\r\nHost: example\r\n\r\n".encode(),
            b"POST /v1/identity HTTP/1.1\r\nHost: example\r\nContent-Length: 1\r\n\r\nx",
        ]:
            status, _body = await self.request(request)
            self.assertEqual(status, 400)
        self.assertEqual(self.requests, [])

    async def test_health_reports_reachability_without_a_database_http_request(self) -> None:
        status, body = await self.request(b"GET /health HTTP/1.1\r\nHost: example\r\n\r\n")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {"database": DATABASE, "upstream_reachable": True})
        self.assertEqual(self.requests, [])
        self.upstream.close()
        await self.upstream.wait_closed()
        status, body = await self.request(b"GET /health HTTP/1.1\r\nHost: example\r\n\r\n")
        self.assertEqual(status, 503)
        self.assertFalse(json.loads(body)["upstream_reachable"])

    async def test_identity_bootstrap_is_empty_and_does_not_forward_caller_credentials(
        self,
    ) -> None:
        status, body = await self.request(
            b"POST /v1/identity HTTP/1.1\r\nHost: example\r\nAuthorization: Bearer test-secret\r\nContent-Length: 0\r\n\r\n"
        )
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {"token": "abc"})
        self.assertNotIn(b"test-secret", self.requests[-1])
        self.assertIn(b"Content-Length: 0\r\n", self.requests[-1])
        self.identity_chunked = True
        status, body = await self.request(b"POST /v1/identity HTTP/1.1\r\nHost: example\r\n\r\n")
        self.assertEqual((status, json.loads(body)), (200, {"token": "abc"}))

    async def test_oversized_identity_response_and_headers_are_bounded(self) -> None:
        self.identity_oversized = True
        status, _body = await self.request(b"POST /v1/identity HTTP/1.1\r\nHost: example\r\n\r\n")
        self.assertEqual(status, 502)
        status, _body = await self.request(
            b"GET /health HTTP/1.1\r\nHost: example\r\nX-Huge: "
            + b"a" * gateway_module.HEADER_LIMIT
            + b"\r\n\r\n"
        )
        self.assertEqual(status, 431)

    async def test_empty_chunked_identity_is_normalized_before_forwarding(self) -> None:
        status, body = await self.request(
            b"POST /v1/identity HTTP/1.1\r\nHost: example\r\n"
            b"Transfer-Encoding: chunked\r\nAuthorization: Bearer test-secret\r\n\r\n0\r\n\r\n"
        )
        self.assertEqual((status, json.loads(body)), (200, {"token": "abc"}))
        self.assertEqual(len(self.requests), 1)
        self.assertIn(b"Content-Length: 0\r\n", self.requests[0])
        self.assertNotIn(b"Transfer-Encoding", self.requests[0])
        self.assertNotIn(b"test-secret", self.requests[0])
        self.assertTrue(self.requests[0].endswith(b"Connection: close\r\n\r\n"))

    async def test_chunked_identity_rejects_data_trailers_and_ambiguous_framing(self) -> None:
        prefix = b"POST /v1/identity HTTP/1.1\r\nHost: example\r\nTransfer-Encoding: chunked\r\n"
        for request in [
            prefix + b"Content-Length: 0\r\n\r\n0\r\n\r\n",
            prefix + b"\r\n1\r\nx\r\n0\r\n\r\n",
            prefix + b"\r\n0;extension=true\r\n\r\n",
            prefix + b"\r\n0\r\nX-Trailer: value\r\n\r\n",
            prefix.replace(b"chunked", b"gzip, chunked") + b"\r\n0\r\n\r\n",
        ]:
            status, _body = await self.request(request)
            self.assertEqual(status, 400)
        self.assertEqual(self.requests, [])

    async def test_stalled_chunked_identity_body_times_out_without_upstream_request(self) -> None:
        with patch.object(gateway_module, "HEADER_TIMEOUT", 0.05):
            status, _body = await self.request(
                b"POST /v1/identity HTTP/1.1\r\nHost: example\r\nTransfer-Encoding: chunked\r\n\r\n"
            )
            self.assertEqual(status, 408)
        self.assertEqual(self.requests, [])

    async def test_stalled_headers_timeout(self) -> None:
        with patch.object(gateway_module, "HEADER_TIMEOUT", 0.05):
            reader, writer = await self.connect()
            writer.write(b"GET /health HTTP/1.1\r\n")
            await writer.drain()
            response = await asyncio.wait_for(reader.read(), 1)
        self.assertTrue(response.startswith(b"HTTP/1.1 408 "))

    async def test_real_websocket_frames_large_binary_and_early_data_are_transferred(self) -> None:
        reader, writer = await self.connect()
        query = "?connection_id=" + "a" * 32 + "&compression=None&confirmed=false"
        writer.write(
            handshake(PATH + query, "Authorization: Bearer test-secret\r\n")
            + frame(b"early", masked=True)
        )
        await writer.drain()
        response = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 2)
        self.assertTrue(response.startswith(b"HTTP/1.1 101 "))
        self.assertEqual(await read_frame(reader), (2, b"early"))
        self.assertIn(query.encode(), self.requests[-1])
        self.assertIn(b"authorization: Bearer test-secret\r\n", self.requests[-1])
        payload = bytes(range(256)) * 8192
        writer.write(frame(payload, masked=True))
        await writer.drain()
        self.assertEqual(await asyncio.wait_for(read_frame(reader), 5), (2, payload))
        writer.write(frame(b"", masked=True, opcode=8))
        await writer.drain()
        self.assertEqual(await read_frame(reader), (8, b""))
        self.assertEqual(await asyncio.wait_for(reader.read(), 2), b"")

    async def test_eof_allows_final_upstream_bytes_then_closes(self) -> None:
        self.send_on_eof = True
        reader, writer = await self.connect()
        writer.write(handshake())
        await writer.drain()
        await reader.readuntil(b"\r\n\r\n")
        writer.write_eof()
        self.assertEqual(
            await asyncio.wait_for(read_frame(reader), 2), (2, b"last-message-after-eof")
        )
        self.assertEqual(await asyncio.wait_for(reader.read(), 2), b"")

    async def test_upstream_rejection_never_starts_a_byte_tunnel(self) -> None:
        self.upstream_status = 403
        status, body = await self.request(handshake() + frame(b"not-authorized", masked=True))
        self.assertEqual((status, body), (403, b"{}"))

    async def test_shutdown_closes_an_active_websocket(self) -> None:
        reader, writer = await self.connect()
        writer.write(handshake())
        await writer.drain()
        await reader.readuntil(b"\r\n\r\n")
        await asyncio.wait_for(self.gateway.close(), 3)
        self.assertEqual(await asyncio.wait_for(reader.read(), 2), b"")
        self.assertEqual(self.gateway.handlers, set())

    async def test_sigterm_cleans_readiness_file_and_active_websocket(self) -> None:
        with tempfile.TemporaryDirectory(prefix="mt2-gateway-test-") as directory:
            ready_file = Path(directory) / "ready.json"
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                str(Path(gateway_module.__file__).resolve()),
                "--database",
                DATABASE,
                "--upstream",
                f"http://127.0.0.1:{self.gateway.config.upstream_port}",
                "--listen-port",
                "0",
                "--ready-file",
                str(ready_file),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                output = await asyncio.wait_for(process.stdout.readline(), 5)
                ready = json.loads(output)["gateway_ready"]
                self.assertEqual(ready["pid"], process.pid)
                self.assertEqual(ready["database"], DATABASE)
                self.assertEqual(json.loads(ready_file.read_text()), ready)
                port = int(ready["url"].rsplit(":", 1)[1])
                reader, writer = await asyncio.open_connection("127.0.0.1", port)
                self.writers.append(writer)
                writer.write(handshake())
                await writer.drain()
                response = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 2)
                self.assertTrue(response.startswith(b"HTTP/1.1 101 "))
                process.terminate()
                await asyncio.wait_for(process.wait(), 5)
                self.assertEqual(process.returncode, 0)
                self.assertEqual(await asyncio.wait_for(reader.read(), 2), b"")
                self.assertFalse(ready_file.exists())
                self.assertEqual(await process.stderr.read(), b"")
                with self.assertRaises(OSError):
                    await asyncio.open_connection("127.0.0.1", port)
            finally:
                if process.returncode is None:
                    process.kill()
                    await process.wait()

    async def test_backpressure_blocks_further_reads_until_writer_drains(self) -> None:
        reader = asyncio.StreamReader()
        reader.feed_data(b"a" * (gateway_module.CHUNK_SIZE * 3))
        reader.feed_eof()
        release = asyncio.Event()

        class SlowWriter:
            count = 0

            def write(self, data: bytes) -> None:
                self.count += len(data)

            async def drain(self) -> None:
                await release.wait()

            def can_write_eof(self) -> bool:
                return False

        writer = SlowWriter()
        task = asyncio.create_task(gateway_module.pump(reader, writer))
        await asyncio.sleep(0.025)
        self.assertFalse(task.done())
        self.assertEqual(writer.count, gateway_module.CHUNK_SIZE)
        release.set()
        await asyncio.wait_for(task, 1)
        self.assertEqual(writer.count, gateway_module.CHUNK_SIZE * 3)


if __name__ == "__main__":
    unittest.main()
