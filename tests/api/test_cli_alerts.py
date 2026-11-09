"""`finops-agent test-alerts`: one message through each channel that's set up, and a clear word on each."""

import argparse

import httpx
import pytest


@pytest.fixture
def settings(api_env, monkeypatch):
    from finops_api.config import get_settings

    s = get_settings()
    for name in ("smtp_host", "smtp_user", "alert_email_to", "bale_bot_token", "bale_chat_id"):
        monkeypatch.setattr(s, name, None)
    return s


@pytest.fixture
def smtp(monkeypatch):
    sent = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            self.host = host

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def starttls(self):
            pass

        def login(self, user, password):
            pass

        def send_message(self, msg):
            if self.host == "down.example.ir":
                raise ConnectionRefusedError("connection refused")
            sent.append(msg)

    monkeypatch.setattr("finops_api.alerts.smtplib.SMTP", FakeSMTP)
    return sent


def run(**kw):
    from finops_api.cli import cmd_test_alerts

    cmd_test_alerts(argparse.Namespace(to=kw.get("to")))


def test_nothing_set_up_says_how(settings):
    with pytest.raises(SystemExit) as e:
        run()
    assert "SMTP_HOST" in str(e.value) and "BALE" in str(e.value)


def test_email_goes_to_the_alert_address_or_the_one_given(settings, smtp, monkeypatch, capsys):
    monkeypatch.setattr(settings, "smtp_host", "mail.example.ir")
    monkeypatch.setattr(settings, "alert_email_to", "ops@example.ir")
    run()
    run(to="me@example.ir")
    assert [m["To"] for m in smtp] == ["ops@example.ir", "me@example.ir"]
    assert "sent to ops@example.ir" in capsys.readouterr().out


def test_a_failing_channel_exits_with_an_error(settings, smtp, monkeypatch, capsys):
    monkeypatch.setattr(settings, "smtp_host", "down.example.ir")
    monkeypatch.setattr(settings, "alert_email_to", "ops@example.ir")
    with pytest.raises(SystemExit) as e:
        run()
    assert e.value.code == 1
    assert "ConnectionRefusedError" in capsys.readouterr().out


def test_bale_failures_never_print_the_bot_token(settings, monkeypatch, capsys):
    monkeypatch.setattr(settings, "bale_bot_token", "123:secret-token")
    monkeypatch.setattr(settings, "bale_chat_id", "42")

    def refuse(url, **kw):
        request = httpx.Request("POST", url)
        raise httpx.HTTPStatusError(f"401 for {url}", request=request, response=httpx.Response(401, request=request))

    monkeypatch.setattr("finops_api.alerts.httpx.post", refuse)
    with pytest.raises(SystemExit):
        run()
    out = capsys.readouterr().out
    assert "HTTP 401" in out and "secret-token" not in out
