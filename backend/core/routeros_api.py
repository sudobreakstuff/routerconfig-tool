"""RouterOS API protocol client (MikroTik).

Implements the RouterOS binary API on port 8728 (plain) / 8729 (TLS). Lets the
app manage MikroTik routers through their native API when SSH is not exposed,
which is common for routers reachable only over WinBox/API ports.

Protocol summary (https://help.mikrotik.com/docs/spaces/ROS/pages/47579160/API):
- A sentence is a sequence of length-prefixed words terminated by an empty word.
- Lengths: <0x80 -> 1 byte; <0x4000 -> 2 bytes (first OR 0x80);
  <0x200000 -> 3 bytes (first OR 0xC0); else 4 bytes (first OR 0xE0).
- Login: send `/login`. If the reply contains `=ret=<hex>`, use MD5
  challenge-response: md5(b'\\x00' + password + unhexlify(ret)), hexdigest
  prefixed with "00". RouterOS >= 6.43 also accepts plaintext
  `/login =name=.. =password=..`.
"""
from __future__ import annotations

import asyncio
import binascii
import hashlib
import ssl


class RouterOSAPIError(Exception):
    """Base error for RouterOS API communication."""


class RouterOSAPILoginError(RouterOSAPIError):
    """Authentication failed."""


def _encode_length(n: int) -> bytes:
    if n < 0x80:
        return bytes([n])
    if n < 0x4000:
        return bytes([0x80 | (n >> 8), n & 0xFF])
    if n < 0x200000:
        return bytes([0xC0 | (n >> 16), (n >> 8) & 0xFF, n & 0xFF])
    return bytes([0xE0 | (n >> 24), (n >> 16) & 0xFF, (n >> 8) & 0xFF, n & 0xFF])


def _encode_word(word: bytes) -> bytes:
    return _encode_length(len(word)) + word


class RouterOSAPI:
    """Async RouterOS API client."""

    def __init__(self, host: str, username: str = "admin", password: str = "",
                 port: int | None = None, use_ssl: bool = False,
                 timeout: int = 15, ssl_verify: bool = False):
        self.host = host
        self.username = username
        self.password = password
        self.use_ssl = use_ssl
        self.port = port or (8729 if use_ssl else 8728)
        self.timeout = timeout
        self.ssl_verify = ssl_verify
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._buffer = bytearray()

    async def connect(self) -> None:
        try:
            if self.use_ssl:
                context = ssl.create_default_context()
                if not self.ssl_verify:
                    context.check_hostname = False
                    context.verify_mode = ssl.CERT_NONE
                self._reader, self._writer = await asyncio.wait_for(
                    asyncio.open_connection(
                        self.host, self.port, ssl=context, server_hostname=self.host
                    ),
                    timeout=self.timeout,
                )
            else:
                self._reader, self._writer = await asyncio.wait_for(
                    asyncio.open_connection(self.host, self.port),
                    timeout=self.timeout,
                )
        except (OSError, asyncio.TimeoutError) as e:
            raise RouterOSAPIError(f"RouterOS API connection failed: {e}") from e

        try:
            await self.login()
        except RouterOSAPILoginError:
            await self.close()
            raise
        except Exception as e:
            await self.close()
            raise RouterOSAPIError(f"RouterOS API error: {e}") from e

    async def login(self) -> None:
        """Authenticate. Tries plaintext first (6.43+), falls back to MD5 challenge."""
        plaintext_ok = await self._try_login(plaintext=True)
        if not plaintext_ok:
            if not await self._try_login(plaintext=False):
                raise RouterOSAPILoginError("RouterOS API authentication failed (invalid credentials)")

    async def _try_login(self, plaintext: bool) -> bool:
        try:
            if plaintext:
                reply = await self._sentence(
                    [b"/login", b"=name=" + self.username.encode(),
                     b"=password=" + self.password.encode()]
                )
                return self._done(reply)
            reply = await self._sentence([b"/login"])
            ret = None
            for sent in reply:
                for w in sent:
                    if w.startswith(b"=ret="):
                        ret = w[5:]
            if ret is None:
                return False
            token = binascii.unhexlify(ret)
            hasher = hashlib.md5()
            hasher.update(b"\x00")
            hasher.update(self.password.encode())
            hasher.update(token)
            response = b"00" + hasher.hexdigest().encode("ascii")
            final = await self._sentence(
                [b"/login", b"=name=" + self.username.encode(), b"=response=" + response]
            )
            return self._done(final)
        except Exception:
            return False

    @staticmethod
    def _done(reply: list[list[bytes]]) -> bool:
        for sent in reply:
            for w in sent:
                if w == b"!done":
                    return True
        return False

    async def call(self, command: str, **params) -> list[dict]:
        """Execute a command, e.g. call('/system/resource/print').

        Returns a list of records parsed from `!re` reply sentences.
        """
        cmd = command.encode()
        words = [cmd]
        for k, v in params.items():
            if v is None:
                continue
            words.append(f"={k}={v}".encode())
        reply = await self._sentence(words)
        records: list[dict] = []
        for sent in reply:
            if not sent:
                continue
            first = sent[0]
            if first == b"!re" or first == b"!done":
                record: dict = {}
                for w in sent[1:]:
                    if w.startswith(b"="):
                        kv = w[1:].decode(errors="replace")
                        if "=" in kv:
                            k, _, v = kv.partition("=")
                            record[k] = v
                        else:
                            record[kv] = ""
                    elif w.startswith(b"!"):
                        continue
                if first == b"!re" and record:
                    records.append(record)
                elif first == b"!done":
                    records.append(record)
            elif first == b"!trap":
                msg = ""
                for w in sent[1:]:
                    if w.startswith(b"=message="):
                        msg = w[9:].decode(errors="replace")
                raise RouterOSAPIError(f"RouterOS API error: {msg or 'unknown trap'}")
        return records

    async def close(self) -> None:
        if self._writer:
            try:
                self._writer.close()
                await asyncio.wait_for(self._writer.wait_closed(), timeout=3)
            except Exception:
                pass
        self._writer = None
        self._reader = None
        self._buffer.clear()

    async def _sentence(self, words: list[bytes]) -> list[list[bytes]]:
        if self._writer is None:
            raise RouterOSAPIError("Not connected")
        payload = b"".join(_encode_word(w) for w in words) + b"\x00"
        self._writer.write(payload)
        await self._writer.drain()
        return await self._read_sentences()

    async def _read_sentences(self) -> list[list[bytes]]:
        sentences: list[list[bytes]] = []
        while True:
            words = await self._read_sentence()
            if words is None:
                break
            if not words:
                continue
            first = words[0]
            sentences.append(words)
            # Reply blocks are terminated by !done (success), !trap (error),
            # or !fatal (connection closing). !re rows precede the terminator.
            if first in (b"!done", b"!trap", b"!fatal"):
                break
        return sentences

    async def _read_sentence(self) -> list[bytes] | None:
        words: list[bytes] = []
        while True:
            word = await self._read_word()
            if word is None:
                return None if not words else words
            if word == b"":
                return words
            words.append(word)

    async def _read_word(self) -> bytes | None:
        while True:
            length = await self._read_length()
            if length is None:
                return None
            data = await self._read_exact(length)
            if data is None:
                return None
            if length == 0:
                return b""
            return bytes(data)

    async def _read_length(self) -> int | None:
        first = await self._read_byte()
        if first is None:
            return None
        if first < 0x80:
            return first
        if first < 0xC0:
            second = await self._read_byte()
            if second is None:
                return None
            return ((first & 0x3F) << 8) | second
        if first < 0xE0:
            rest = await self._read_bytes(2)
            if rest is None:
                return None
            return ((first & 0x1F) << 16) | (rest[0] << 8) | rest[1]
        rest = await self._read_bytes(4)
        if rest is None:
            return None
        return ((first & 0x0F) << 24) | (rest[0] << 16) | (rest[1] << 8) | rest[2]

    async def _read_byte(self) -> int | None:
        data = await self._read_exact(1)
        return data[0] if data else None

    async def _read_exact(self, n: int) -> bytearray | None:
        while len(self._buffer) < n:
            if self._reader is None:
                return None
            try:
                chunk = await asyncio.wait_for(self._reader.read(65536), timeout=self.timeout)
            except (asyncio.TimeoutError, OSError):
                return None
            if not chunk:
                return None
            self._buffer.extend(chunk)
        out = bytearray(self._buffer[:n])
        del self._buffer[:n]
        return out

    async def _read_bytes(self, n: int) -> bytes | None:
        data = await self._read_exact(n)
        return bytes(data) if data is not None else None
