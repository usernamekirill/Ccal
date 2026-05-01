"""Async TCP health endpoint (GET /health -> 200 ``ok``)."""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)

_HEALTH_BODY = b"ok"
_HEALTH_RESPONSE = (
    b"HTTP/1.1 200 OK\r\n"
    b"Content-Type: text/plain; charset=utf-8\r\n"
    b"Content-Length: "
    + str(len(_HEALTH_BODY)).encode("ascii")
    + b"\r\nConnection: close\r\n\r\n"
    + _HEALTH_BODY
)
_NOT_FOUND = b"HTTP/1.1 404 Not Found\r\nConnection: close\r\n\r\n"


async def handle_health_client(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
) -> None:
    try:
        first_line = await reader.readline()
        if first_line.startswith(b"GET /health") or first_line.startswith(b"GET /health?"):
            writer.write(_HEALTH_RESPONSE)
        else:
            writer.write(_NOT_FOUND)
        await writer.drain()
    finally:
        writer.close()
        await writer.wait_closed()


async def run_health_server(host: str, port: int) -> None:
    """Serve ``GET /health`` until cancelled."""
    server = await asyncio.start_server(handle_health_client, host, port, reuse_address=True)
    logger.info("Health check listening on %s:%s", host, port)
    try:
        async with server:
            await server.serve_forever()
    except asyncio.CancelledError:
        logger.info("Health check server stopped")
        raise


def start_health_server_task(host: str, port: int) -> asyncio.Task[None]:
    """Background task; cancel on shutdown."""
    return asyncio.create_task(run_health_server(host, port), name="health_check")
