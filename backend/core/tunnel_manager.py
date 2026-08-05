"""SSH tunnel manager - opens real port-forwards through a jump host (CPE)
and keeps track of each tunnel's lifecycle so they can be listed and closed.

Each tunnel forwards a random local port to a downstream target's port (default 80)
by opening SSH `direct-tcpip` channels through the persistent connection pool.
"""
import asyncio
import random
import select
import socket
import threading
import time

from core.connection_pool import pool

DEFAULT_IDLE_TIMEOUT = 120  # seconds without a connection before auto-close

_tunnels: dict[int, dict] = {}
_next_id = 1
_lock = threading.Lock()


def _create_tunnel(ssh, target: str, target_port: int, local_port: int):
    """Spin up the socket forwarder. Returns a stop() callback."""
    stop_event = threading.Event()

    def copy_loop(src, dst):
        try:
            while not stop_event.is_set():
                r, _, _ = select.select([src, dst], [], [], 0.5)
                if not r:
                    continue
                for fd in r:
                    data = fd.recv(8192)
                    if not data:
                        return
                    (dst if fd is src else src).sendall(data)
        except Exception:
            pass
        finally:
            try:
                src.close()
            except Exception:
                pass
            try:
                dst.close()
            except Exception:
                pass

    def forward():
        try:
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind(("127.0.0.1", local_port))
            server.listen(5)
            while not stop_event.is_set():
                try:
                    conn, _ = server.accept()
                except (TimeoutError, OSError):
                    continue
                try:
                    chan = ssh.get_transport().open_channel(
                        "direct-tcpip", (target, target_port), ("127.0.0.1", 0)
                    )
                except Exception:
                    try:
                        conn.close()
                    except Exception:
                        pass
                    continue
                threading.Thread(target=copy_loop, args=(conn, chan), daemon=True).start()
                threading.Thread(target=copy_loop, args=(chan, conn), daemon=True).start()
        except Exception:
            pass
        finally:
            try:
                server.close()
            except Exception:
                pass

    thread = threading.Thread(target=forward, daemon=True)
    thread.start()
    return stop_event


async def open_tunnel(host: str, username: str, password: str,
                      target: str, target_port: int = 80,
                      idle_timeout: int = DEFAULT_IDLE_TIMEOUT) -> dict:
    """Open a tunnel through `host` to `target:target_port`. Returns metadata."""
    global _next_id
    ssh = await asyncio.get_event_loop().run_in_executor(
        None, pool.get, host, username, password, 22
    )

    _s, _o, _e = ssh.exec_command(f"ping -c 1 -W 2 {target} 2>&1", timeout=6)
    out = _o.read().decode(errors="replace")
    if "bytes from" not in out.lower():
        raise ValueError(f"Target {target} not reachable from CPE. Check routing.")

    free = await asyncio.get_event_loop().run_in_executor(None, _find_free_port)
    stop_event = _create_tunnel(ssh, target, target_port, free)

    tid = _next_id
    _next_id += 1
    entry = {
        "id": tid,
        "host": host,
        "target": target,
        "target_port": target_port,
        "url": f"http://127.0.0.1:{free}",
        "port": free,
        "opened_at": time.time(),
        "last_active": time.time(),
        "idle_timeout": idle_timeout,
        "_stop": stop_event,
    }
    with _lock:
        _tunnels[tid] = entry
    return _public(entry)


def close_tunnel(tunnel_id: int) -> bool:
    with _lock:
        entry = _tunnels.pop(tunnel_id, None)
    if not entry:
        return False
    entry["_stop"].set()
    return True


def list_tunnels() -> list[dict]:
    with _lock:
        _prune()
        return [_public(e) for e in _tunnels.values()]


def _prune():
    now = time.time()
    for tid in list(_tunnels.keys()):
        e = _tunnels[tid]
        if now - e["last_active"] > e["idle_timeout"]:
            e["_stop"].set()
            del _tunnels[tid]


def _public(entry: dict) -> dict:
    return {
        "id": entry["id"],
        "host": entry["host"],
        "target": entry["target"],
        "target_port": entry["target_port"],
        "url": entry["url"],
        "port": entry["port"],
        "opened_at": entry["opened_at"],
        "idle_timeout": entry["idle_timeout"],
    }


def _find_free_port() -> int:
    for _ in range(50):
        candidate = random.randint(10000, 20000)
        if _port_free(candidate):
            return candidate
    raise RuntimeError("No free local ports available for tunnel")


def _port_free(port: int) -> bool:
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        probe.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        probe.close()