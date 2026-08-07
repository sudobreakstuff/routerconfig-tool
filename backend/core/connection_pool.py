"""Persistent SSH connection pool - one connection per device, reused for all commands."""
import asyncio
import threading
import time

import paramiko

from core.ssh_compat import create_ssh_client


class ConnectionPool:
    def __init__(self):
        self._connections: dict[str, dict] = {}
        self._lock = threading.Lock()

    def get(self, host: str, username: str, password: str, port: int = 22) -> paramiko.SSHClient:
        key = f"{username}@{host}:{port}"
        with self._lock:
            if key in self._connections:
                entry = self._connections[key]
                try:
                    transport = entry["ssh"].get_transport()
                    if transport and transport.is_active():
                        entry["last_used"] = time.time()
                        return entry["ssh"]
                except Exception:
                    pass
                # Connection dead, remove it
                self._disconnect(key)

            # Open new connection
            ssh = create_ssh_client()
            ssh.connect(host, port=port, username=username, password=password, timeout=15, banner_timeout=10)
            self._connections[key] = {"ssh": ssh, "last_used": time.time()}
            return ssh

    def disconnect(self, host: str, username: str, password: str, port: int = 22):
        key = f"{username}@{host}:{port}"
        with self._lock:
            self._disconnect(key)

    def _disconnect(self, key: str):
        entry = self._connections.pop(key, None)
        if entry:
            try: entry["ssh"].close()
            except Exception: pass

    def disconnect_all(self):
        with self._lock:
            for key in list(self._connections.keys()):
                self._disconnect(key)

    async def execute(self, host: str, username: str, password: str, command: str,
                      port: int = 22, timeout: int = 15) -> str:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._execute_sync, host, username, password, command, port, timeout
        )

    def _execute_sync(self, host: str, username: str, password: str, command: str,
                      port: int, timeout: int) -> str:
        ssh = self.get(host, username, password, port)
        stdin, stdout, stderr = ssh.exec_command(command, timeout=timeout)
        try:
            stdout.channel.recv_exit_status()
        except Exception:
            pass
        return stdout.read().decode(errors="replace").strip()


pool = ConnectionPool()
