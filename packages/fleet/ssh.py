"""The only network code for server monitoring: one fixed read-only exchange over SSH.

Nothing here can send a command chosen by a caller. The server's forced command decides what runs.
"""

from __future__ import annotations

import io
import socket
from dataclasses import dataclass

import paramiko
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .collector import COLLECTOR_USER

MAX_OUTPUT_BYTES = 64 * 1024


class SshError(RuntimeError):
    """The server could not be reached or refused the key."""


class HostKeyChanged(SshError):
    """The server's identity differs from the one remembered. Never connect through this automatically."""


@dataclass
class CollectResult:
    output: str
    host_key: str


def generate_keypair() -> tuple[str, str]:
    """(private key in OpenSSH format, public key line)."""
    key = Ed25519PrivateKey.generate()
    private = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.OpenSSH,
                                serialization.NoEncryption()).decode()
    public = key.public_key().public_bytes(serialization.Encoding.OpenSSH, serialization.PublicFormat.OpenSSH).decode()
    return private, public


def collect(host: str, port: int, private_key: str, known_host_key: str | None, timeout: float = 15.0) -> CollectResult:
    """Connect, check the server's identity, and read the collector's output. The first successful connection
    establishes the identity; after that a different key is refused."""
    pkey = paramiko.Ed25519Key.from_private_key(io.StringIO(private_key))
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
    except OSError as exc:
        raise SshError(f"cannot reach {host}:{port}: {exc}") from exc
    transport = paramiko.Transport(sock)
    try:
        transport.banner_timeout = timeout
        transport.start_client(timeout=timeout)
        remote = transport.get_remote_server_key()
        host_key = f"{remote.get_name()} {remote.get_base64()}"
        if known_host_key and known_host_key != host_key:
            raise HostKeyChanged(f"the SSH identity of {host} has changed")
        transport.auth_publickey(COLLECTOR_USER, pkey)
        channel = transport.open_session(timeout=timeout)
        channel.settimeout(timeout)
        channel.exec_command("collect")
        output = bytearray()
        while len(output) < MAX_OUTPUT_BYTES:
            chunk = channel.recv(4096)
            if not chunk:
                break
            output += chunk
        status = channel.recv_exit_status()
        if status != 0:
            raise SshError(f"collector exited with status {status}")
        return CollectResult(output.decode("utf-8", errors="replace"), host_key)
    except paramiko.AuthenticationException as exc:
        raise SshError("the server refused the key; run the setup command on it") from exc
    except (paramiko.SSHException, OSError, EOFError) as exc:
        raise SshError(f"SSH failed: {exc}") from exc
    finally:
        transport.close()
