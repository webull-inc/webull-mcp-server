"""Account tools for Webull MCP Server.

Provides: get_account_list, resolve_account, resolve_account_id.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from webull_openapi_mcp.errors import handle_sdk_exception
from webull_openapi_mcp.formatters import (
    extract_response_data,
    format_account_list,
    prepend_disclaimer,
)

if TYPE_CHECKING:
    from fastmcp import FastMCP
    from webull_openapi_mcp.audit import AuditLogger
    from webull_openapi_mcp.sdk_client import WebullSDKClient


def normalize_account_id(account_id: str | None) -> str | None:
    """Normalize opaque account IDs to strings for SDK calls.

    Accepts only ``str`` (or ``None``).  The MCP tool schema exposes
    ``account_id`` as a pure string so that large numeric IDs are never
    silently truncated by JSON integer precision limits.
    """
    if account_id is None:
        return None
    if not isinstance(account_id, str):
        raise ValueError("account_id must be a string")
    return account_id


def register_account_tools(
    mcp: FastMCP,
    sdk: WebullSDKClient,
    audit: AuditLogger,
) -> None:
    """Register account-related tools."""

    @mcp.tool(
        description=(
            "Get all linked accounts. "
            "Returns: account_id, user_id, account_number, account_type, account_class, account_label."
        ),
        annotations={"readOnlyHint": True},
    )
    async def get_account_list() -> str:
        """Get all linked accounts."""
        audit.log_tool_call("get_account_list", {})
        try:
            response = sdk.trade.account_v2.get_account_list()
            data = extract_response_data(response)
            return prepend_disclaimer(format_account_list(data))
        except Exception as e:
            return handle_sdk_exception(e, "get_account_list")


def _validate_explicit_account(
    accounts: list[dict], account_id: str, valid_labels: set[str], asset_type: str,
) -> dict | None:
    """Validate an explicitly provided account_id against the required labels.

    Raises ValueError if the account type doesn't match. Returns the matched
    account, or None if the account_id is absent from account_list.
    """
    for acct in accounts:
        if str(acct.get("account_id")) == account_id:
            label = acct.get("account_label", "")
            if label and label not in valid_labels:
                expected = ", ".join(sorted(valid_labels))
                raise ValueError(
                    f"Account '{account_id}' (label: {label}) does not support {asset_type} trading. "
                    f"Required account types: {expected}. "
                    f"Please use get_account_list to find the correct account."
                )
            return acct
    # account_id not found in list — let it through, API will reject if invalid
    return None


def _auto_select_account(
    accounts: list[dict], valid_labels: set[str], asset_type: str,
) -> dict:
    """Auto-select an account matching the required labels."""
    matching = [
        acct for acct in accounts
        if acct.get("account_label", "") in valid_labels
    ]

    if len(matching) == 1:
        return matching[0]

    if len(matching) > 1:
        acct_list = ", ".join(
            f"{a['account_id']} ({a.get('account_label', 'N/A')})"
            for a in matching
        )
        raise ValueError(
            f"Multiple {asset_type} accounts found: {acct_list}. "
            f"Please specify account_id explicitly."
        )

    expected = ", ".join(sorted(valid_labels))
    raise ValueError(
        f"No account found for {asset_type} trading. "
        f"Required account types: {expected}."
    )


async def resolve_account(
    sdk: WebullSDKClient,
    asset_type: str,
    account_id: str | None = None,
) -> dict:
    """Resolve and validate the correct account for a given asset type.

    - If account_id is provided, validates it matches the required asset type.
    - If not provided, auto-selects the first matching account.
    - For single-account setups (e.g., HK region), uses that account directly.
    - If multiple matching accounts exist, refuses to auto-select.
    """
    from webull_openapi_mcp.constants import ASSET_TYPE_ACCOUNT_LABELS

    valid_labels = ASSET_TYPE_ACCOUNT_LABELS.get(asset_type)
    if valid_labels is None:
        raise ValueError(f"Unknown asset_type '{asset_type}'")

    response = sdk.trade.account_v2.get_account_list()
    accounts = extract_response_data(response)

    if not accounts or not isinstance(accounts, list):
        raise ValueError("No accounts found. Please check your API credentials.")

    normalized_account_id = normalize_account_id(account_id)

    if normalized_account_id is not None:
        account = _validate_explicit_account(
            accounts,
            normalized_account_id,
            valid_labels,
            asset_type,
        )
        return account if account is not None else {"account_id": normalized_account_id}

    if len(accounts) == 1:
        return accounts[0]

    return _auto_select_account(accounts, valid_labels, asset_type)


async def resolve_account_id(
    sdk: WebullSDKClient,
    asset_type: str,
    account_id: str | None = None,
) -> str:
    """Resolve and validate the correct account_id for a given asset type."""
    account = await resolve_account(sdk, asset_type, account_id)
    return str(account["account_id"])
