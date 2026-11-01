"""Real SSH against an in-process server: key checks and the remembered server identity."""

import io
import socket
import threading
import time

import paramiko
import pytest

from fleet import HostKeyChanged, SshError, collect, generate_keypair

OUTPUT = "cpu_cores=2\n"


class _Server(paramiko.ServerInterface):
    def __init__(self, allowed):
        self.allowed = allowed
        self.commands = []
        self.done = threading.Event()

    def check_auth_publickey(self, username, key):
        ok = username == "finops-collector" and key.get_base64() == self.allowed
        return paramiko.AUTH_SUCCESSFUL if ok else paramiko.AUTH_FAILED

    def get_allowed_auths(self, username):
        return "publickey"

    def check_channel_request(self, kind, chanid):
        return paramiko.OPEN_SUCCEEDED

    def check_channel_exec_request(self, channel, command):
        self.commands.append(command)

        def reply():
            time.sleep(0.1)  # a real sshd acknowledges the request before the command finishes
            channel.send(OUTPUT)
            channel.send_exit_status(0)
            channel.close()

        threading.Thread(target=reply, daemon=True).start()
        return True


@pytest.fixture
def ssh_server():
    private, public = generate_keypair()
    host_key = paramiko.Ed25519Key.from_private_key(io.StringIO(generate_keypair()[0]))
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(5)
    listener.settimeout(10)
    handler = _Server(public.split()[1])
    transports = []

    def serve():
        while True:
            try:
                conn, _ = listener.accept()
            except OSError:
                return
            t = paramiko.Transport(conn)
            t.add_server_key(host_key)
            transports.append(t)
            try:
                t.start_server(server=handler)
            except (EOFError, paramiko.SSHException):
                continue  # the client hung up on purpose, as with a changed identity

    threading.Thread(target=serve, daemon=True).start()
    yield listener.getsockname()[1], private, f"{host_key.get_name()} {host_key.get_base64()}", handler
    listener.close()
    for t in transports:
        t.close()


def test_reads_output_and_returns_server_identity(ssh_server):
    port, private, identity, handler = ssh_server
    result = collect("127.0.0.1", port, private, None)
    assert result.output == OUTPUT
    assert result.host_key == identity
    assert handler.commands == [b"collect"]


def test_known_identity_is_accepted(ssh_server):
    port, private, identity, _ = ssh_server
    assert collect("127.0.0.1", port, private, identity).output == OUTPUT


def test_changed_identity_is_refused_before_authenticating(ssh_server):
    port, private, _, handler = ssh_server
    with pytest.raises(HostKeyChanged):
        collect("127.0.0.1", port, private, "ssh-ed25519 AAAAdifferent")
    assert handler.commands == []


def test_wrong_key_is_reported_as_needing_setup(ssh_server):
    port, _, _, _ = ssh_server
    with pytest.raises(SshError, match="setup command"):
        collect("127.0.0.1", port, generate_keypair()[0], None)


def test_unreachable_server_is_a_clean_error():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    with pytest.raises(SshError, match="cannot reach"):
        collect("127.0.0.1", port, generate_keypair()[0], None, timeout=2)
