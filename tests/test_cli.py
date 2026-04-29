"""Tests for the command-line interface."""

from __future__ import annotations

import sys
from types import ModuleType

from webull_openapi_mcp import cli
from webull_openapi_mcp.config import ServerConfig


def _config(**overrides: object) -> ServerConfig:
    defaults = dict(app_key="test_key", app_secret="test_secret")
    defaults.update(overrides)
    return ServerConfig(**defaults)


def test_webull_mcp_banner_is_ascii_and_includes_runtime_context() -> None:
    banner = cli._build_webull_mcp_banner(
        _config(region_id="jp", environment="prod")
    )

    assert banner.isascii()
    assert "WEBULL OPENAPI MCP" in banner
    assert "ASCII-safe startup banner" not in banner
    assert "Webull OpenAPI MCP Server" not in banner
    assert "Region     : JP" in banner
    assert "Environment: PROD" in banner
    assert "Transport  : stdio" in banner


def test_serve_prints_custom_banner_and_disables_fastmcp_banner(
    monkeypatch,
    capsys,
) -> None:
    config = _config(region_id="hk", environment="uat")
    run_calls: list[dict[str, object]] = []

    class FakeServer:
        def run(self, **kwargs: object) -> None:
            run_calls.append(kwargs)

    monkeypatch.setattr(cli, "load_config", lambda env_file: config)
    monkeypatch.setattr(cli, "validate_config", lambda config: None)
    monkeypatch.setattr(cli, "_check_token_status", lambda config: None)

    fake_server_module = ModuleType("webull_openapi_mcp.server")
    fake_server_module.build_server = lambda config: FakeServer()
    monkeypatch.setitem(sys.modules, "webull_openapi_mcp.server", fake_server_module)

    assert cli.serve.callback is not None
    cli.serve.callback(None)

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "WEBULL OPENAPI MCP" in captured.err
    assert captured.err.isascii()
    assert run_calls == [{"transport": "stdio", "show_banner": False}]
