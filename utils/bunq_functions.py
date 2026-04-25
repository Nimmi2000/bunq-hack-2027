"""
Clean callable wrappers around the bunq API.
All functions authenticate automatically using the BUNQ_API_KEY env var.
If BUNQ_API_KEY is not set, a sandbox user is created automatically.
"""

import os
import sys

# Make BunqClient importable when this file is called from the project root
sys.path.insert(0, os.path.dirname(__file__))
from bunq_client import BunqClient


def _client() -> BunqClient:
    api_key = os.environ.get("BUNQ_API_KEY", "").strip()
    if not api_key:
        api_key = BunqClient.create_sandbox_user()
        os.environ["BUNQ_API_KEY"] = api_key  # cache for the process lifetime
    c = BunqClient(api_key=api_key, sandbox=True)
    c.authenticate()
    return c


_SANDBOX_IBAN_CACHE: dict[str, str] = {}   # name  → IBAN
_SANDBOX_NAME_CACHE: dict[str, str] = {}   # IBAN  → display name


def _sandbox_recipient_iban(name: str) -> str:
    """Create a fresh sandbox user and return their IBAN (cached per name)."""
    key = name.strip().lower()
    if key in _SANDBOX_IBAN_CACHE:
        return _SANDBOX_IBAN_CACHE[key]

    api_key = BunqClient.create_sandbox_user()
    c = BunqClient(api_key=api_key, sandbox=True)
    c.authenticate()

    raw = c.get(f"user/{c.user_id}/monetary-account")
    for item in raw:
        for acc in item.values():
            for alias in acc.get("alias", []):
                if alias.get("type") == "IBAN":
                    iban = alias["value"]
                    _SANDBOX_IBAN_CACHE[key] = iban
                    _SANDBOX_NAME_CACHE[iban] = name.strip()  # remember the real name
                    return iban

    raise RuntimeError("Could not retrieve IBAN for sandbox recipient")


def list_accounts() -> list[dict]:
    """Return all monetary accounts with id, description, balance, currency, and IBAN."""
    c = _client()
    raw = c.get(f"user/{c.user_id}/monetary-account")
    result = []
    for item in raw:
        account_type = next(iter(item))
        acc = item[account_type]
        ibans = [a["value"] for a in acc.get("alias", []) if a.get("type") == "IBAN"]
        balance = acc.get("balance", {})
        result.append(
            {
                "id": acc.get("id"),
                "type": account_type,
                "description": acc.get("description"),
                "status": acc.get("status"),
                "balance": balance.get("value"),
                "currency": balance.get("currency"),
                "iban": ibans[0] if ibans else None,
            }
        )
    return result


def list_transactions(count: int = 10) -> list[dict]:
    """Return the most recent payment transactions for the primary account."""
    c = _client()
    account_id = c.get_primary_account_id()
    raw = c.get(
        f"user/{c.user_id}/monetary-account/{account_id}/payment",
        params={"count": min(int(count), 200)},
    )
    result = []
    for item in raw:
        p = item.get("Payment", {})
        cp_alias = p.get("counterparty_alias", {})
        cp_iban = cp_alias.get("iban") or cp_alias.get("value", "")
        cp_name = _SANDBOX_NAME_CACHE.get(cp_iban) or cp_alias.get("display_name")
        result.append(
            {
                "id": p.get("id"),
                "date": p.get("created", "")[:19],
                "amount": p.get("amount", {}).get("value"),
                "currency": p.get("amount", {}).get("currency"),
                "counterparty": cp_name,
                "description": p.get("description"),
                "type": p.get("type"),
            }
        )
    return result


def make_payment(
    amount: str,
    currency: str,
    recipient_name: str,
    recipient_email: str | None = None,
    description: str = "Payment from Finn",
) -> dict:
    """
    Send money to a recipient. If only recipient_name is provided, infer a sandbox email.
    Returns a confirmation dict with payment_id and status.
    """
    if not recipient_email:
        guessed = recipient_name.strip().lower().replace(' ', '.').replace("@", "")
        recipient_email = f"{guessed or 'recipient'}@example.com"

    c = _client()
    account_id = c.get_primary_account_id()

    sandbox = os.environ.get("BUNQ_SANDBOX", "true").strip().lower() not in ("false", "0")
    if sandbox:
        iban = _sandbox_recipient_iban(recipient_name or recipient_email or "recipient")
        counterparty = {"type": "IBAN", "value": iban, "name": recipient_name or recipient_email}
    else:
        counterparty = {"type": "EMAIL", "value": recipient_email, "name": recipient_name or recipient_email}

    resp = c.post(
        f"user/{c.user_id}/monetary-account/{account_id}/payment",
        {
            "amount": {"value": str(amount), "currency": currency},
            "counterparty_alias": counterparty,
            "description": description,
        },
    )
    payment_id = resp[0]["Id"]["id"]
    return {
        "payment_id": payment_id,
        "amount": amount,
        "currency": currency,
        "recipient": recipient_name or recipient_email,
        "recipient_email": recipient_email,
        "description": description,
        "status": "sent",
    }


def request_money(
    amount: str,
    currency: str,
    counterparty_name: str,
    counterparty_email: str | None = None,
    description: str = "Payment request from Finn",
) -> dict:
    """
    Create a payment request (RequestInquiry) asking someone to pay you.
    If only a counterparty name is provided, infer a sandbox email.
    Returns the request_id and status.
    """
    if not counterparty_email:
        guessed = counterparty_name.strip().lower().replace(' ', '.').replace("@", "")
        counterparty_email = f"{guessed or 'payer'}@example.com"

    c = _client()
    account_id = c.get_primary_account_id()

    sandbox = os.environ.get("BUNQ_SANDBOX", "true").strip().lower() not in ("false", "0")
    if sandbox:
        iban = _sandbox_recipient_iban(counterparty_name or counterparty_email or "payer")
        counterparty = {"type": "IBAN", "value": iban, "name": counterparty_name or counterparty_email}
    else:
        counterparty = {"type": "EMAIL", "value": counterparty_email, "name": counterparty_name or counterparty_email}

    resp = c.post(
        f"user/{c.user_id}/monetary-account/{account_id}/request-inquiry",
        {
            "amount_inquired": {"value": str(amount), "currency": currency},
            "counterparty_alias": counterparty,
            "description": description,
            "allow_bunqme": False,
        },
    )
    request_id = resp[0]["Id"]["id"]
    return {
        "request_id": request_id,
        "amount": amount,
        "currency": currency,
        "from": counterparty_name or counterparty_email,
        "description": description,
        "status": "pending",
    }


def create_payment_link(amount: str, currency: str, description: str) -> dict:
    """
    Create a shareable bunq.me payment link.
    Returns the share URL, tab_id, and status.
    """
    c = _client()
    account_id = c.get_primary_account_id()

    resp = c.post(
        f"user/{c.user_id}/monetary-account/{account_id}/bunqme-tab",
        {
            "bunqme_tab_entry": {
                "amount_inquired": {"value": str(amount), "currency": currency},
                "description": description,
            }
        },
    )
    tab_id = resp[0]["Id"]["id"]

    tab_data = c.get(
        f"user/{c.user_id}/monetary-account/{account_id}/bunqme-tab/{tab_id}"
    )
    tab = tab_data[0]["BunqMeTab"]

    return {
        "tab_id": tab_id,
        "share_url": tab.get("bunqme_tab_share_url", "(no URL in sandbox)"),
        "amount": amount,
        "currency": currency,
        "description": description,
        "status": tab.get("status"),
    }
