"""Persistent connection pool - one connection per device, reused for all commands.

Prefers SSH, then falls back to the WinBox terminal protocol (port 8291) so
MikroTik routers that only expose WinBox still work through the same API.
"""
import asyncio
import threading
import time

import paramiko

from core.ssh_compat import create_ssh_client


class WinBoxAdapter:
    """Thin wrapper exposing exec_command/close over a WinBox terminal client,
    so the pool can treat WinBox connections like SSH ones."""

    def __init__(self, host: str, username: str, password: str, port: int = 8291,
                 timeout: int = 15):
        self.host = host
        self.username = username
        self.password = password
        self.port = port
        self.timeout = timeout
        self._client = None

    def open(self):
        from core.winbox_terminal import WinboxTerminalClient
        client = WinboxTerminalClient(self.host, port=self.port, timeout=min(self.timeout, 12))
        client.connect()
        client.authenticate(self.username, self.password)
        client.open_terminal(self.password, 120, 40)
        self._client = client

    def exec_command(self, command: str, timeout: int = 15):
        if self._client is None:
            self.open()
        return self._client.exec_command(command, timeout=timeout)

    def close(self):
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None

    def get_transport(self):
        return getattr(self._client, "socket", None)


class ConnectionPool:
    def __init__(self):
        self._connections: dict[str, dict] = {}
        self._lock = threading.Lock()

    def _key(self, host: str, username: str, password: str, port: int) -> str:
        return f"{username}@{host}:{port}"

    def get(self, host: str, username: str, password: str, port: int = 22,
            winbox_port: int = 8291):
        key = self._key(host, username, password, port)
        with self._lock:
            if key in self._connections:
                entry = self._connections[key]
                try:
                    conn = entry["conn"]
                    if isinstance(conn, paramiko.SSHClient):
                        transport = conn.get_transport()
                        if transport and transport.is_active():
                            entry["last_used"] = time.time()
                            return conn
                    else:
                        if conn._client is not None:
                            entry["last_used"] = time.time()
                            return conn
                except Exception:
                    pass
                # Connection dead, remove it
                self._disconnect(key)

            # Try SSH first
            try:
                ssh = create_ssh_client()
                ssh.connect(host, port=port, username=username, password=password,
                            timeout=15, banner_timeout=10)
                self._connections[key] = {"conn": ssh, "last_used": time.time()}
                return ssh
            except Exception:
                pass

            # Fall back to WinBox terminal protocol (MikroTik's management port)
            try:
                wb = WinBoxAdapter(host, username, password, winbox_port)
                wb.open()
                self._connections[key] = {"conn": wb, "last_used": time.time()}
                return wb
            except Exception:
                raise

    def disconnect(self, host: str, username: str, password: str, port: int = 22):
        key = self._key(host, username, password, port)
        with self._lock:
            self._disconnect(key)

    def _disconnect(self, key: str):
        entry = self._connections.pop(key, None)
        if entry:
            try:
                entry["conn"].close()
            except Exception:
                pass

    def disconnect_all(self):
        with self._lock:
            for key in list(self._connections.keys()):
                self._disconnect(key)

    async def execute(self, host: str, username: str, password: str, command: str,
                      port: int = 22, timeout: int = 15, winbox_port: int = 8291) -> str:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._execute_sync, host, username, password, command, port, timeout, winbox_port
        )

    def _execute_sync(self, host: str, username: str, password: str, command: str,
                      port: int, timeout: int, winbox_port: int = 8291) -> str:
        conn = self.get(host, username, password, port, winbox_port)
        if isinstance(conn, paramiko.SSHClient):
            stdin, stdout, stderr = conn.exec_command(command, timeout=timeout)
            try:
                stdout.channel.recv_exit_status()
            except Exception:
                pass
            return stdout.read().decode(errors="replace").strip()
        return conn.exec_command(command, timeout=timeout)


pool = ConnectionPool()
