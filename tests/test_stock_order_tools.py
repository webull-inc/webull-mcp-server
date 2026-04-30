"""Unit tests for stock order payload construction."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from webull_openapi_mcp.config import ServerConfig
from webull_openapi_mcp.errors import ValidationError
from webull_openapi_mcp.tools.trading.stock_order import (
    _build_modify_order,
    _build_preview_stock_order,
    _build_stock_order,
    _extract_close_contracts_from_order_detail,
    _validate_jp_replace_close_contracts_against_order_detail,
    _validate_jp_margin_type_account,
    _validate_jp_position_intent,
    _validate_replace_close_contracts_match_original,
    _validate_replace_close_contracts,
)


def _config(**overrides) -> ServerConfig:
    defaults = dict(app_key="test_key", app_secret="test_secret", region_id="jp")
    defaults.update(overrides)
    return ServerConfig(**defaults)


def test_build_stock_order_includes_jp_place_fields():
    close_contracts = [{"contract_id": "contract-1", "quantity": "10"}]

    order = _build_stock_order({
        "coid": "cid-1",
        "market": "US",
        "symbol": "AAPL",
        "side": "SELL",
        "order_type": "LIMIT",
        "time_in_force": "DAY",
        "entrust_type": "QTY",
        "trading_session": "CORE",
        "quantity": 10,
        "limit_price": 123.45,
        "account_tax_type": "GENERAL",
        "margin_type": "ONE_DAY",
        "position_intent": "SELL_TO_CLOSE",
        "close_contracts": close_contracts,
    })

    assert order["client_order_id"] == "cid-1"
    assert order["account_tax_type"] == "GENERAL"
    assert order["margin_type"] == "ONE_DAY"
    assert order["position_intent"] == "SELL_TO_CLOSE"
    assert order["close_contracts"] == close_contracts
    assert order["quantity"] == "10"
    assert order["limit_price"] == "123.45"


def test_build_preview_stock_order_includes_jp_preview_fields():
    close_contracts = [{"contract_id": "contract-2", "quantity": "5"}]

    order = _build_preview_stock_order({
        "coid": "cid-2",
        "market": "JP",
        "symbol": "7203",
        "side": "SELL",
        "order_type": "MARKET",
        "time_in_force": "DAY",
        "trading_session": "CORE",
        "quantity": 5,
        "account_tax_type": "SPECIFIC",
        "margin_type": "INDEFINITE",
        "close_contracts": close_contracts,
    })

    assert order["client_order_id"] == "cid-2"
    assert order["market"] == "JP"
    assert order["account_tax_type"] == "SPECIFIC"
    assert order["margin_type"] == "INDEFINITE"
    assert order["close_contracts"] == close_contracts
    assert order["quantity"] == "5"


def test_build_modify_order_includes_jp_close_contracts():
    close_contracts = [{"contract_id": "contract-3", "quantity": "3"}]

    modify_order = _build_modify_order({
        "client_order_id": "cid-3",
        "quantity": 3,
        "close_contracts": close_contracts,
    })

    assert modify_order["client_order_id"] == "cid-3"
    assert modify_order["close_contracts"] == close_contracts
    assert modify_order["quantity"] == "3"


def test_validate_replace_close_contracts_rejects_invalid_jp_payload():
    with pytest.raises(ValidationError) as exc_info:
        _validate_replace_close_contracts(
            _config(),
            [{"contract_id": "contract-4", "quantity": "0"}],
            None,
        )

    assert exc_info.value.field == "close_contracts"


def test_validate_replace_close_contracts_checks_batch_orders_for_jp():
    with pytest.raises(ValidationError) as exc_info:
        _validate_replace_close_contracts(
            _config(),
            None,
            [{"client_order_id": "cid-5", "close_contracts": "bad"}],
        )

    assert exc_info.value.field == "close_contracts"


def test_validate_replace_close_contracts_ignores_non_jp_regions():
    _validate_replace_close_contracts(
        _config(region_id="us"),
        [{"contract_id": "contract-6", "quantity": "0"}],
        None,
    )


def test_validate_replace_close_contracts_allows_cash_account_payload():
    _validate_replace_close_contracts(
        _config(),
        [{"contract_id": "contract-7", "quantity": "1"}],
        None,
    )


def test_extract_close_contracts_from_nested_order_detail():
    detail = {
        "client_order_id": "wrapper-id",
        "orders": [
            {
                "client_order_id": "cid-8",
                "close_contracts": [{"contract_id": "contract-8", "quantity": "10"}],
            }
        ],
    }

    assert _extract_close_contracts_from_order_detail(detail, "cid-8") == [
        {"contract_id": "contract-8", "quantity": "10"}
    ]


def test_extract_close_contracts_from_single_nested_order_without_child_client_id():
    detail = {
        "client_order_id": "cid-8b",
        "orders": [
            {"close_contracts": [{"contract_id": "contract-8b", "quantity": "10"}]}
        ],
    }

    assert _extract_close_contracts_from_order_detail(detail, "cid-8b") == [
        {"contract_id": "contract-8b", "quantity": "10"}
    ]


def test_replace_close_contracts_requires_payload_when_original_has_close_contracts():
    with pytest.raises(ValidationError) as exc_info:
        _validate_replace_close_contracts_match_original(
            [{"contract_id": "contract-9", "quantity": "10"}],
            None,
        )

    assert exc_info.value.field == "close_contracts"


def test_replace_close_contracts_rejects_size_change():
    with pytest.raises(ValidationError) as exc_info:
        _validate_replace_close_contracts_match_original(
            [
                {"contract_id": "contract-10", "quantity": "10"},
                {"contract_id": "contract-11", "quantity": "5"},
            ],
            [{"contract_id": "contract-10", "quantity": "8"}],
        )

    assert exc_info.value.field == "close_contracts"


def test_replace_close_contracts_rejects_contract_id_change():
    with pytest.raises(ValidationError) as exc_info:
        _validate_replace_close_contracts_match_original(
            [{"contract_id": "contract-12", "quantity": "10"}],
            [{"contract_id": "contract-13", "quantity": "8"}],
        )

    assert exc_info.value.field == "close_contracts"


def test_replace_close_contracts_allows_quantity_change_only():
    _validate_replace_close_contracts_match_original(
        [{"contract_id": "contract-14", "quantity": "10"}],
        [{"contract_id": "contract-14", "quantity": "8"}],
    )


def test_replace_close_contracts_allows_reordered_contract_ids():
    _validate_replace_close_contracts_match_original(
        [
            {"contract_id": "contract-14a", "quantity": "10"},
            {"contract_id": "contract-14b", "quantity": "5"},
        ],
        [
            {"contract_id": "contract-14b", "quantity": "3"},
            {"contract_id": "contract-14a", "quantity": "8"},
        ],
    )


def test_jp_replace_close_contracts_fetches_original_detail():
    sdk = MagicMock()
    sdk.trade.order_v3.get_order_detail.return_value = {
        "orders": [
            {
                "client_order_id": "cid-15",
                "close_contracts": [{"contract_id": "contract-15", "quantity": "10"}],
            }
        ]
    }

    _validate_jp_replace_close_contracts_against_order_detail(
        _config(),
        sdk,
        "account-1",
        [
            {
                "client_order_id": "cid-15",
                "close_contracts": [{"contract_id": "contract-15", "quantity": "6"}],
            }
        ],
    )

    sdk.trade.order_v3.get_order_detail.assert_called_once_with(
        account_id="account-1",
        client_order_id="cid-15",
    )


def test_jp_margin_type_account_allows_absent_value_for_cash():
    _validate_jp_margin_type_account(_config(), "CASH", None)


def test_jp_margin_type_account_allows_margin_account():
    _validate_jp_margin_type_account(
        _config(),
        "US_MARGIN",
        "ONE_DAY",
    )


def test_jp_margin_type_account_rejects_margin_type_for_cash():
    with pytest.raises(ValidationError) as exc_info:
        _validate_jp_margin_type_account(_config(), "CASH", "ONE_DAY")

    assert exc_info.value.field == "margin_type"


def test_jp_position_intent_allows_absent_value_for_cash():
    _validate_jp_position_intent(_config(), "CASH", None)


def test_jp_position_intent_allows_margin_account():
    _validate_jp_position_intent(_config(), "US_MARGIN", "BUY_TO_OPEN")


def test_jp_position_intent_rejects_invalid_value():
    with pytest.raises(ValidationError) as exc_info:
        _validate_jp_position_intent(_config(), "US_MARGIN", "OPEN")

    assert exc_info.value.field == "position_intent"


def test_jp_position_intent_rejects_cash_account():
    with pytest.raises(ValidationError) as exc_info:
        _validate_jp_position_intent(_config(), "CASH", "SELL_TO_CLOSE")

    assert exc_info.value.field == "position_intent"
