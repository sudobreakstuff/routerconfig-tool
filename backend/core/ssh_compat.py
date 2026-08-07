"""SSH client compatibility helpers.

Modern paramiko (>= 3.4) drops legacy host-key algorithms (``ssh-dss``) by
default, which breaks connections to older routers that only offer DSA or
SHA-1 RSA host keys. We restore those algorithms globally so every SSH
connection in the app negotiates successfully with legacy hardware while still
preferring modern algorithms when the peer supports them.
"""
from __future__ import annotations

import paramiko
from paramiko.transport import Transport

_LEGACY_KEYS = ("ssh-rsa", "ssh-dss")

if not hasattr(Transport, "_ssh_compat_patched"):
    _current = tuple(Transport._preferred_keys)
    _missing = tuple(k for k in _LEGACY_KEYS if k not in _current)
    if _missing:
        Transport._preferred_keys = _current + _missing
    Transport._ssh_compat_patched = True


def create_ssh_client() -> paramiko.SSHClient:
    """Create a paramiko SSH client that accepts legacy host keys."""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    return client
