"""Tests for the SSH tunnel manager lifecycle (no live SSH needed).

We exercise the manager's bookkeeping and port-allocator directly by faking the
SSH client, and verify open/list/close semantics.
"""

import threading
import time

from core import tunnel_manager


class FakeSSH:
    def __init__(self):
        self._closed = False

    def exec_command(self, command, timeout=5):
        import io
        out = io.BytesIO(b"64 bytes from 192.168.1.5: icmp_seq=1 ttl=64 time=0.5 ms")
        return None, out, io.BytesIO(b"")

    def get_transport(self):
        return FakeTransport()

    def close(self):
        self._closed = True


class FakeTransport:
    def open_channel(self, kind, dest, src):
        return FakeChannel()


class FakeChannel:
    def recv(self, n):
        return b""

    def sendall(self, data):
        return None

    def close(self):
        return None


def test_open_list_close_roundtrip():
    ssh = FakeSSH()
    tunnel_manager.pool.get = lambda *a, **k: ssh

    import asyncio
    result = asyncio.run(
        tunnel_manager.open_tunnel("10.0.0.1", "admin", "x", "192.168.1.5", target_port=80, idle_timeout=999)
    )

    assert result["target"] == "192.168.1.5"
    assert result["url"].startswith("http://127.0.0.1:")
    assert result["port"] > 0

    tunnels = tunnel_manager.list_tunnels()
    assert any(t["id"] == result["id"] for t in tunnels)

    assert tunnel_manager.close_tunnel(result["id"]) is True
    # second close fails
    assert tunnel_manager.close_tunnel(result["id"]) is False
    assert tunnel_manager.list_tunnels() == []


def test_find_free_port_returns_bindable_port():
    assert tunnel_manager._port_free(tunnel_manager._find_free_port()) is True
