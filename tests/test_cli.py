import sys
import json
from unittest.mock import patch

from handelsregister.cli import main as cli_main
from handelsregister.client import Handelsregister


def test_fetch_json(capsys, sample_organization_response, monkeypatch):
    def fake_fetch(self, q, features=None, ai_search=None):
        return sample_organization_response

    monkeypatch.setattr(Handelsregister, "fetch_organization", fake_fetch)
    monkeypatch.setenv("HANDELSREGISTER_API_KEY", "x")
    monkeypatch.setattr(sys, "argv", ["prog", "fetch", "json", "KONUX GmbH"])
    cli_main()
    out = capsys.readouterr().out
    assert json.loads(out) == sample_organization_response


def test_fetch_text(capsys, sample_organization_response, monkeypatch):
    def fake_fetch(self, q, features=None, ai_search=None):
        return sample_organization_response

    monkeypatch.setattr(Handelsregister, "fetch_organization", fake_fetch)
    monkeypatch.setenv("HANDELSREGISTER_API_KEY", "x")
    monkeypatch.setattr(sys, "argv", ["prog", "fetch", "KONUX GmbH"])
    cli_main()
    out = capsys.readouterr().out.strip()
    assert "KONUX GmbH" in out
    assert "Status: ACTIVE" in out
