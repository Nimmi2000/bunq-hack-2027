"""
Voice pipeline:
  audio → Amazon Nova Sonic (STT, aws-sdk-bedrock-runtime + SigV4)
        → Amazon Bedrock Converse (tool use, bearer token)
        → bunq function
        → natural language reply

Required environment variables:
  BUNQ_API_KEY             bunq API key
  AWS_ACCESS_KEY_ID        IAM access key  (for Nova Sonic STT)
  AWS_SECRET_ACCESS_KEY    IAM secret key  (for Nova Sonic STT)
  AWS_BEDROCK_API_KEY      bearer token    (for Bedrock Converse)

Optional:
  AWS_REGION               default: us-east-1
  BEDROCK_STT_MODEL_ID     default: amazon.nova-sonic-v1:0
  BEDROCK_MODEL_ID         default: amazon.nova-lite-v1:0
"""

import asyncio
import base64
import concurrent.futures
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import uuid

from dotenv import load_dotenv
load_dotenv()

import requests as _http

from aws_sdk_bedrock_runtime.client import (
    BedrockRuntimeClient,
    InvokeModelWithBidirectionalStreamOperationInput,
)
from aws_sdk_bedrock_runtime.models import (
    InvokeModelWithBidirectionalStreamInputChunk,
    BidirectionalInputPayloadPart,
)
from aws_sdk_bedrock_runtime.config import Config
from smithy_aws_core.identity.environment import EnvironmentCredentialsResolver

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "utils"))
from bunq_functions import (
    create_payment_link,
    list_accounts,
    list_transactions,
    make_payment,
    request_money,
)

# ── Configuration ─────────────────────────────────────────────────────────────

AWS_REGION      = os.environ.get("AWS_REGION", "us-east-1")
STT_MODEL_ID    = os.environ.get("BEDROCK_STT_MODEL_ID", "amazon.nova-sonic-v1:0")
MODEL_ID        = os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-opus-4-7")
BEDROCK_KEY     = os.environ.get("AWS_BEDROCK_API_KEY", "").strip().strip('"')
TEXT_LLM_API_KEY   = os.environ.get("TEXT_LLM_API_KEY", "").strip().strip('"')
TEXT_LLM_MODEL_ID  = os.environ.get("TEXT_LLM_MODEL_ID", "amazon.nova-pro-v1:0")

SYSTEM_PROMPT = (
    "You are Finn, bunq's friendly AI banking assistant. The user's name is Eva. "
    "When the user makes a banking request, ALWAYS call the appropriate tool — never ask follow-up questions. "
    "Infer ALL missing values: email → firstname.lastname@example.com lowercase; currency → EUR; description → 'Payment to <name>'. "
    "If the amount is missing or zero, use '0.00' and the caller will ask the user. "
    "If recipient name is given but no email, derive it: 'Sriram' → 'sriram@example.com', 'John Doe' → 'john.doe@example.com'. "
    "You MUST call a tool for any send/pay/transfer/request intent — never respond with text for these. "
    "For greetings or capability questions where no tool is needed, reply in 1-2 sentences. "
    "All responses will be read aloud — keep them short, natural, and conversational."
)

# ── Tool definitions for Bedrock Converse ─────────────────────────────────────

TOOLS: list[dict] = [
    {
        "toolSpec": {
            "name": "list_accounts",
            "description": "List all monetary accounts with balances, currencies, and IBANs.",
            "inputSchema": {
                "json": {"type": "object", "properties": {}, "required": []}
            },
        }
    },
    {
        "toolSpec": {
            "name": "list_transactions",
            "description": "Retrieve recent payment transactions for the primary account.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "count": {
                            "type": "integer",
                            "description": "Number of transactions to fetch (1-200, default 10).",
                        }
                    },
                    "required": [],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "make_payment",
            "description": "Send money from Eva's account to a recipient by email.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "amount":          {"type": "string", "description": "Decimal amount, e.g. '10.00'."},
                        "currency":        {"type": "string", "description": "ISO currency code, e.g. 'EUR'."},
                        "recipient_email": {"type": "string", "description": "Recipient email address."},
                        "recipient_name":  {"type": "string", "description": "Recipient display name."},
                        "description":     {"type": "string", "description": "Payment note."},
                    },
                    "required": ["amount", "currency", "description"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "request_money",
            "description": "Ask someone to pay Eva by sending them a payment request.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "amount":               {"type": "string", "description": "Amount to request, e.g. '25.00'."},
                        "currency":             {"type": "string", "description": "ISO currency code."},
                        "counterparty_email":   {"type": "string", "description": "Payer's email."},
                        "counterparty_name":    {"type": "string", "description": "Payer's display name."},
                        "description":          {"type": "string", "description": "Reason for the request."},
                    },
                    "required": ["amount", "currency", "description"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "create_payment_link",
            "description": "Create a shareable bunq.me link anyone can use to pay Eva.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "amount":      {"type": "string", "description": "Requested amount, e.g. '5.00'."},
                        "currency":    {"type": "string", "description": "ISO currency code."},
                        "description": {"type": "string", "description": "What the link is for."},
                    },
                    "required": ["amount", "currency", "description"],
                }
            },
        }
    },
]

FUNCTION_MAP = {
    "list_accounts":       list_accounts,
    "list_transactions":   list_transactions,
    "make_payment":        make_payment,
    "request_money":       request_money,
    "create_payment_link": create_payment_link,
}

# ── Anthropic tool definitions (used when TEXT_LLM_API_KEY is set) ────────────

ANTHROPIC_TOOLS: list[dict] = [
    {
        "name": "list_accounts",
        "description": "List all monetary accounts with balances, currencies, and IBANs.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "list_transactions",
        "description": "Retrieve recent payment transactions for the primary account.",
        "input_schema": {
            "type": "object",
            "properties": {
                "count": {
                    "type": "integer",
                    "description": "Number of transactions to fetch (1-200, default 10).",
                }
            },
            "required": [],
        },
    },
    {
        "name": "make_payment",
        "description": "Send money from Eva's account to a recipient by email.",
        "input_schema": {
            "type": "object",
            "properties": {
                "amount":          {"type": "string", "description": "Decimal amount, e.g. '10.00'."},
                "currency":        {"type": "string", "description": "ISO currency code, e.g. 'EUR'."},
                "recipient_email": {"type": "string", "description": "Recipient email address."},
                "recipient_name":  {"type": "string", "description": "Recipient display name."},
                "description":     {"type": "string", "description": "Payment note."},
            },
            "required": ["amount", "currency", "recipient_email", "description"],
        },
    },
    {
        "name": "request_money",
        "description": "Ask someone to pay Eva by sending them a payment request.",
        "input_schema": {
            "type": "object",
            "properties": {
                "amount":             {"type": "string", "description": "Amount to request, e.g. '25.00'."},
                "currency":           {"type": "string", "description": "ISO currency code."},
                "counterparty_email": {"type": "string", "description": "Payer's email."},
                "counterparty_name":  {"type": "string", "description": "Payer's display name."},
                "description":        {"type": "string", "description": "Reason for the request."},
            },
            "required": ["amount", "currency", "counterparty_email", "description"],
        },
    },
    {
        "name": "create_payment_link",
        "description": "Create a shareable bunq.me link anyone can use to pay Eva.",
        "input_schema": {
            "type": "object",
            "properties": {
                "amount":      {"type": "string", "description": "Requested amount, e.g. '5.00'."},
                "currency":    {"type": "string", "description": "ISO currency code."},
                "description": {"type": "string", "description": "What the link is for."},
            },
            "required": ["amount", "currency", "description"],
        },
    },
]

SESSION_MEMORY: dict[str, dict] = {}

REQUIRED_FIELDS = {
    "make_payment": ["amount", "currency", "recipient_name", "recipient_email", "description"],
    "request_money": ["amount", "currency", "counterparty_name", "counterparty_email", "description"],
    "create_payment_link": ["amount", "currency", "description"],
}


def _get_session_state(session_id: str) -> dict:
    return SESSION_MEMORY.setdefault(
        session_id,
        {"tool": None, "input": {}, "pending": False},
    )


def _merge_memory(tool: str, tool_input: dict, session_state: dict) -> dict:
    if session_state and session_state.get("tool") == tool:
        merged = {**session_state.get("input", {}), **tool_input}
        return merged
    return tool_input


def _save_session_state(session_id: str, tool: str, tool_input: dict, pending: bool = True) -> None:
    SESSION_MEMORY[session_id] = {
        "tool": tool,
        "input": tool_input,
        "pending": pending,
    }


# ── Step 1: Speech-to-Text via Amazon Nova Sonic ──────────────────────────────

def _to_pcm16k(audio_bytes: bytes, media_format: str) -> bytes:
    """Convert any audio format to 16 kHz mono 16-bit raw PCM via ffmpeg."""
    if shutil.which("ffmpeg") is None:
        raise EnvironmentError(
            "ffmpeg executable not found. Install ffmpeg and add it to your PATH."
        )

    suffix = f".{media_format.split(';')[0].strip()}"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(audio_bytes)
        tmp = f.name
    try:
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", tmp,
             "-ar", "16000", "-ac", "1", "-f", "s16le", "-"],
            capture_output=True, check=True,
        )
        return result.stdout
    except FileNotFoundError as exc:
        raise EnvironmentError(
            "ffmpeg executable not found. Install ffmpeg and add it to your PATH."
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"ffmpeg conversion failed: {exc.stderr[:300].decode('utf-8', errors='replace')}"
        ) from exc
    finally:
        os.unlink(tmp)


async def _nova_sonic_stt(audio_bytes: bytes, media_format: str) -> str:
    """Stream audio to Nova Sonic and return the USER transcript."""
    pcm = _to_pcm16k(audio_bytes, media_format)

    config = Config(
        endpoint_uri=f"https://bedrock-runtime.{AWS_REGION}.amazonaws.com",
        region=AWS_REGION,
        aws_credentials_identity_resolver=EnvironmentCredentialsResolver(),
    )
    client = BedrockRuntimeClient(config=config)
    stream = await client.invoke_model_with_bidirectional_stream(
        InvokeModelWithBidirectionalStreamOperationInput(model_id=STT_MODEL_ID)
    )

    prompt_name = str(uuid.uuid4())
    sys_name    = str(uuid.uuid4())
    audio_name  = str(uuid.uuid4())

    async def _send(event_dict: dict):
        chunk = InvokeModelWithBidirectionalStreamInputChunk(
            value=BidirectionalInputPayloadPart(
                bytes_=json.dumps(event_dict).encode("utf-8")
            )
        )
        await stream.input_stream.send(chunk)

    async def _sender():
        await _send({"event": {"sessionStart": {
            "inferenceConfiguration": {"maxTokens": 512, "topP": 0.9, "temperature": 0.0}
        }}})
        await _send({"event": {"promptStart": {
            "promptName": prompt_name,
            "textOutputConfiguration": {"mediaType": "text/plain"},
            "toolConfiguration": {"tools": []},
        }}})
        # System prompt
        await _send({"event": {"contentStart": {
            "promptName": prompt_name, "contentName": sys_name,
            "role": "SYSTEM", "type": "TEXT", "interactive": False,
            "textInputConfiguration": {"mediaType": "text/plain"},
        }}})
        await _send({"event": {"textInput": {
            "promptName": prompt_name, "contentName": sys_name,
            "content": "Transcribe the audio exactly. Output only the transcript, nothing else.",
        }}})
        await _send({"event": {"contentEnd": {
            "promptName": prompt_name, "contentName": sys_name,
        }}})
        # Audio content
        await _send({"event": {"contentStart": {
            "promptName": prompt_name, "contentName": audio_name,
            "type": "AUDIO", "interactive": True, "role": "USER",
            "audioInputConfiguration": {
                "mediaType": "audio/lpcm", "sampleRateHertz": 16000,
                "sampleSizeBits": 16, "channelCount": 1,
                "audioType": "SPEECH", "encoding": "base64",
            },
        }}})
        CHUNK = 4096
        for i in range(0, len(pcm), CHUNK):
            await _send({"event": {"audioInput": {
                "promptName": prompt_name, "contentName": audio_name,
                "content": base64.b64encode(pcm[i : i + CHUNK]).decode(),
            }}})
        await _send({"event": {"contentEnd": {
            "promptName": prompt_name, "contentName": audio_name,
        }}})
        await _send({"event": {"promptEnd": {"promptName": prompt_name}}})
        await _send({"event": {"sessionEnd": {}}})
        await stream.input_stream.close()

    transcript   = ""
    current_role = None
    sender_task  = asyncio.create_task(_sender())

    try:
        while True:
            try:
                output = await stream.await_output()
                result = await output[1].receive()
                if result.value and result.value.bytes_:
                    data = json.loads(result.value.bytes_.decode("utf-8"))
                    ev   = data.get("event", {})
                    if "contentStart" in ev:
                        current_role = ev["contentStart"].get("role", "")
                    elif "textOutput" in ev and current_role == "USER":
                        transcript += ev["textOutput"].get("content", "")
            except StopAsyncIteration:
                break
    finally:
        await asyncio.gather(sender_task, return_exceptions=True)

    return transcript.strip() or "[no transcription produced]"


def _run_in_new_loop(coro):
    """Run a coroutine in a brand-new event loop (safe to call from any thread)."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()
        asyncio.set_event_loop(None)


def transcribe_with_nova_sonic(audio_bytes: bytes, media_format: str = "webm") -> str:
    """Synchronous entry-point: runs Nova Sonic STT in an isolated thread/event-loop."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(_run_in_new_loop, _nova_sonic_stt(audio_bytes, media_format)).result()


# ── Step 2+3: Bedrock text model planning + execution ────────────────────────

def _extract_json_object(text: str) -> dict | None:
    """Extract the first JSON object from a model response."""
    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escape = False
    for idx in range(start, len(text)):
        ch = text[idx]
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                json_text = text[start:idx + 1]
                try:
                    return json.loads(json_text)
                except json.JSONDecodeError:
                    return None
    return None


def _invoke_with_text_llm(transcript: str) -> tuple[dict, str]:
    """Use Bedrock Converse API with native tool use to parse the transcript into a plan."""
    bearer = TEXT_LLM_API_KEY or BEDROCK_KEY
    if not bearer:
        raise EnvironmentError("TEXT_LLM_API_KEY or AWS_BEDROCK_API_KEY is required.")

    endpoint = (
        f"https://bedrock-runtime.{AWS_REGION}.amazonaws.com"
        f"/model/{urllib.parse.quote(TEXT_LLM_MODEL_ID, safe='')}/converse"
    )
    headers = {
        "Authorization": f"Bearer {bearer}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    payload = {
        "system": [{"text": SYSTEM_PROMPT}],
        "messages": [{"role": "user", "content": [{"text": transcript}]}],
        "toolConfig": {"tools": TOOLS, "toolChoice": {"any": {}}},
        "inferenceConfig": {"maxTokens": 1024, "temperature": 0.0},
    }
    resp = _http.post(endpoint, json=payload, headers=headers, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    raw = json.dumps(data, ensure_ascii=False)

    content = data.get("output", {}).get("message", {}).get("content", [])
    for block in content:
        if "toolUse" in block:
            tu = block["toolUse"]
            return {"tool": tu.get("name"), "input": tu.get("input", {}), "reply": ""}, raw

    text = "".join(b.get("text", "") for b in content if "text" in b)
    return {"tool": "none", "input": {}, "reply": text.strip()}, raw


def _invoke_model(prompt: str, max_tokens: int = 1024) -> str:
    """Call Bedrock text model using the invoke endpoint."""
    if not BEDROCK_KEY:
        raise EnvironmentError("AWS_BEDROCK_API_KEY is required.")

    endpoint = (
        f"https://bedrock-runtime.{AWS_REGION}.amazonaws.com"
        f"/model/{urllib.parse.quote(MODEL_ID, safe='')}/invoke"
    )
    headers = {
        "Authorization": f"Bearer {BEDROCK_KEY}",
        "Content-Type":  "application/json",
        "Accept":        "application/json",
    }
    payload = {
        "input": prompt,
        "temperature": 0.0,
        "maxTokens": max_tokens,
    }
    resp = _http.post(endpoint, json=payload, headers=headers, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, dict):
        return data.get("output") or data.get("result") or json.dumps(data, ensure_ascii=False)
    return str(data)


def _infer_email_from_name(name: str) -> str:
    name_part = str(name or "").strip().lower()
    name_part = name_part.replace("@", "").replace(" ", ".")
    name_part = name_part.replace("..", ".")
    if not name_part:
        name_part = "recipient"
    return f"{name_part}@example.com"


def _extract_email_from_text(text: str) -> str | None:
    if not text:
        return None
    normalized = text.lower()
    normalized = normalized.replace(" at ", "@").replace(" dot ", ".")
    normalized = normalized.replace(" dot", ".").replace("dot ", ".")
    match = re.search(r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}", normalized)
    return match.group(0) if match else None


def _extract_name_from_text(text: str) -> str | None:
    if not text:
        return None
    patterns = [
        r"(?:to|for|pay|send to|send|transfer to)\s+([A-Za-z][A-Za-z\.\'\-]+(?:\s+[A-Za-z][A-Za-z\.\'\-]+)*)",
        r"(?:request money from|request from|request to)\s+([A-Za-z][A-Za-z\.\'\-]+(?:\s+[A-Za-z][A-Za-z\.\'\-]+)*)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            name = match.group(1).strip()
            if name and len(name) > 1:
                return name
    return None


def _extract_amount_from_text(text: str) -> str | None:
    if not text:
        return None
    focused = text.lower().replace(",", ".")
    patterns = [
        r"€\s*([0-9]+(?:\.[0-9]{1,2})?)",
        r"([0-9]+(?:\.[0-9]{1,2})?)\s*(?:eur|euro|euros)\b",
        r"(?:pay|send|transfer|request)\s*([0-9]+(?:\.[0-9]{1,2})?)",
        r"([0-9]+(?:\.[0-9]{1,2})?)\s*(?:€)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, focused)
        if match:
            return match.group(1).strip()
    return None


def _extract_description_from_text(text: str, name: str | None) -> str | None:
    if not text:
        return None
    match = re.search(r"\bfor\s+([A-Za-z0-9 '\.\-]+?)(?:\.|$)", text, flags=re.IGNORECASE)
    if match:
        desc = match.group(1).strip()
        if desc and not re.search(r"\b(euro|eur|€|to|send|pay|request|money|email|gmail|yahoo)\b", desc, flags=re.IGNORECASE):
            return desc
    if name:
        return f"Payment to {name}" if 'pay' in text.lower() or 'send' in text.lower() else f"Request from {name}"
    return None


def _infer_direct_plan(transcript: str) -> dict | None:
    lower = transcript.lower()
    if not re.search(r"\b(send|pay|transfer|request|ask|invoice|bill)\b", lower):
        return None

    amount = _extract_amount_from_text(transcript)
    if not amount:
        return None

    name = _extract_name_from_text(transcript)
    email = _extract_email_from_text(transcript)
    currency = "EUR"
    description = _extract_description_from_text(transcript, name)

    if re.search(r"\b(request|ask|invoice|bill)\b", lower) and not re.search(r"\b(send|pay|transfer)\b", lower):
        return {
            "tool": "request_money",
            "input": {
                "amount": amount,
                "currency": currency,
                "counterparty_name": name or "recipient",
                "counterparty_email": email or _infer_email_from_name(name or "recipient"),
                "description": description or f"Request from {name or 'recipient'}",
            },
        }

    return {
        "tool": "make_payment",
        "input": {
            "amount": amount,
            "currency": currency,
            "recipient_name": name or "recipient",
            "recipient_email": email or _infer_email_from_name(name or "recipient"),
            "description": description or f"Payment to {name or 'recipient'}",
        },
    }


def _normalize_money_fields(tool: str, tool_input: dict, transcript: str | None = None) -> dict:
    normalized = dict(tool_input)

    if tool in {"make_payment", "request_money", "create_payment_link"}:
        if "currency" not in normalized or not normalized["currency"]:
            normalized["currency"] = "EUR"
        if "amount" in normalized:
            amount = str(normalized["amount"]).strip()
            amount = amount.replace("€", "").replace("eur", "").replace("EUR", "").strip()
            normalized["amount"] = amount

    if transcript:
        if tool == "make_payment":
            if not normalized.get("recipient_email"):
                normalized["recipient_email"] = _extract_email_from_text(transcript)
            if not normalized.get("recipient_name"):
                normalized["recipient_name"] = _extract_name_from_text(transcript)
        if tool == "request_money":
            if not normalized.get("counterparty_email"):
                normalized["counterparty_email"] = _extract_email_from_text(transcript)
            if not normalized.get("counterparty_name"):
                normalized["counterparty_name"] = _extract_name_from_text(transcript)

    if tool == "make_payment":
        if not normalized.get("recipient_email") and normalized.get("recipient_name"):
            normalized["recipient_email"] = _infer_email_from_name(normalized["recipient_name"])
        if not normalized.get("recipient_name") and normalized.get("recipient_email"):
            normalized["recipient_name"] = normalized["recipient_email"].split("@")[0]
        if not normalized.get("description"):
            normalized["description"] = f"Payment to {normalized.get('recipient_name', normalized.get('recipient_email'))}"

    if tool == "request_money":
        if not normalized.get("counterparty_email") and normalized.get("counterparty_name"):
            normalized["counterparty_email"] = _infer_email_from_name(normalized["counterparty_name"])
        if not normalized.get("counterparty_name") and normalized.get("counterparty_email"):
            normalized["counterparty_name"] = normalized["counterparty_email"].split("@")[0]
        if not normalized.get("description"):
            normalized["description"] = f"Request from {normalized.get('counterparty_name', normalized.get('counterparty_email'))}"

    if tool == "create_payment_link":
        if not normalized.get("description"):
            normalized["description"] = "Payment link"

    return normalized


def _format_result(tool: str, result: object) -> str:
    """Convert a tool result into a natural language string for TTS."""
    if isinstance(result, str):
        return result

    if tool == "make_payment" and isinstance(result, dict):
        return (
            f"Done! I've sent {result.get('currency', 'EUR')} {result.get('amount')} "
            f"to {result.get('recipient')}. Payment ID {result.get('payment_id')}."
        )

    if tool == "request_money" and isinstance(result, dict):
        return (
            f"Request sent! I've asked {result.get('from')} to pay you "
            f"{result.get('currency', 'EUR')} {result.get('amount')}. "
            f"Request ID {result.get('request_id')}."
        )

    if tool == "create_payment_link" and isinstance(result, dict):
        url = result.get("share_url", "")
        return (
            f"Payment link created for {result.get('currency', 'EUR')} {result.get('amount')}. "
            f"Share this link: {url}"
        )

    if tool == "list_accounts" and isinstance(result, list):
        if not result:
            return "You have no accounts."
        parts = [
            f"{a.get('description', 'Account')}: "
            f"{a.get('currency', 'EUR')} {a.get('balance', '0')}"
            for a in result if a.get("status") == "ACTIVE"
        ]
        return "Your accounts — " + ", ".join(parts) + "."

    if tool == "list_transactions" and isinstance(result, list):
        if not result:
            return "No recent transactions found."
        lines = []
        for t in result[:5]:
            amt = float(t.get("amount") or 0)
            direction = "sent to" if amt < 0 else "received from"
            lines.append(
                f"{t.get('currency', 'EUR')} {abs(amt):.2f} {direction} "
                f"{t.get('counterparty', 'unknown')}"
            )
        return f"Last {len(lines)} transactions: " + "; ".join(lines) + "."

    return json.dumps(result, ensure_ascii=False)


def _build_action_prompt(transcript: str) -> str:
    return (
        "You are Finn, a Bunq banking assistant. Convert the user's request into a Bunq API action. "
        "Return exactly one JSON object and nothing else. "
        "Do not write any explanation, commentary, or 'thinking' text. "
        "Do not use markdown, code fences, or punctuation outside the JSON object.\n\n"
        "Use only these actions: list_accounts, list_transactions, make_payment, request_money, create_payment_link, none.\n"
        "If the request is about a Bunq action, choose the action and fill tool.input completely. "
        "If the request is only asking for information, use tool=none and provide a short reply.\n\n"
        "Always infer missing values when possible:\n"
        "- If currency is missing for a transfer or request, use EUR.\n"
        "- If description is missing, use 'Payment to {recipient_name}' or 'Request from {counterparty_name}'.\n"
        "- If recipient_email or counterparty_email is missing, infer it as the name converted to lower-case with dots and '@example.com'.\n"
        "- If the user speaks an email like 'sriram at gmail dot com', normalize it to 'sriram@gmail.com'.\n"
        "Never ask follow-up questions when the user already expressed a send or request intent with a recipient and amount.\n\n"
        "JSON format:\n"
        "{\n"
        "  \"tool\": \"list_accounts|list_transactions|make_payment|request_money|create_payment_link|none\",\n"
        "  \"input\": { ... },\n"
        "  \"reply\": \"...\"\n"
        "}\n\n"
        "Examples:\n"
        "Request: Send 50 euros to Shiram.\n"
        "Output: {\"tool\": \"make_payment\", \"input\": {\"amount\": \"50.00\", \"currency\": \"EUR\", \"recipient_name\": \"Shiram\", \"recipient_email\": \"shiram@example.com\", \"description\": \"Payment to Shiram\"}, \"reply\": \"\"}\n"
        "Request: Pay 20 to John Doe for dinner.\n"
        "Output: {\"tool\": \"make_payment\", \"input\": {\"amount\": \"20.00\", \"currency\": \"EUR\", \"recipient_name\": \"John Doe\", \"recipient_email\": \"john.doe@example.com\", \"description\": \"Payment to John Doe\"}, \"reply\": \"\"}\n"
        "Request: Create a payment link for 5 euros.\n"
        "Output: {\"tool\": \"create_payment_link\", \"input\": {\"amount\": \"5.00\", \"currency\": \"EUR\", \"description\": \"Payment link\"}, \"reply\": \"\"}\n\n"
        f"User request: {transcript}"
    )


def parse_and_execute(transcript: str, session_id: str | None = None) -> object:
    """Text-only pipeline: model plans the Bunq action, then backend executes it."""
    session_state = _get_session_state(session_id) if session_id else None

    if TEXT_LLM_API_KEY:
        plan, model_output = _invoke_with_text_llm(transcript)
        plan_source = "text_llm"
        if not plan or plan.get("tool") == "none":
            fallback = _infer_direct_plan(transcript)
            if fallback:
                plan = fallback
                plan_source = "fallback"
    else:
        prompt = _build_action_prompt(transcript)
        model_output = _invoke_model(prompt)
        model_output = re.sub(r"</?thinking>", "", model_output, flags=re.IGNORECASE).strip()
        plan = _extract_json_object(model_output)

        if not plan:
            plan = _infer_direct_plan(transcript)
            plan_source = "fallback"
            if session_state and session_state.get("pending") and session_state.get("tool"):
                plan = {"tool": session_state["tool"], "input": plan.get("input", {}) if plan else {}}
        else:
            plan_source = "model"

    tool = plan.get("tool", "none") or "none"
    tool_input = plan.get("input", {}) or {}
    reply = plan.get("reply", "").strip()

    if session_state:
        tool_input = _merge_memory(tool, tool_input, session_state)

    if tool == "none":
        fallback = _infer_direct_plan(transcript)
        if fallback:
            tool = fallback["tool"]
            tool_input = _merge_memory(tool, fallback["input"], session_state)
            plan_source = "fallback"
        else:
            if any(k in transcript.lower() for k in ["send", "pay", "transfer", "request", "invoice", "charge"]):
                return {
                    "error": "Payment intent detected but model returned none. Please retry with a clear payment request.",
                    "raw_model_output": model_output,
                }
            return reply or {
                "message": "I couldn't detect a direct Bunq action. Please try again with a payment or account request.",
                "raw_model_output": model_output,
            }

    func = FUNCTION_MAP.get(tool)
    if func is None:
        return {
            "error": "Unsupported action",
            "tool": tool,
            "raw_model_output": model_output,
        }

    tool_input = _normalize_money_fields(tool, tool_input, transcript)

    if tool in {"make_payment", "request_money", "create_payment_link"}:
        try:
            amt = float(tool_input.get("amount", 0) or 0)
        except (ValueError, TypeError):
            amt = 0.0
        if amt <= 0:
            return "How much would you like to send? Please say the amount, for example: send 10 euros to Shriram."

    if session_id and tool in REQUIRED_FIELDS:
        _save_session_state(session_id, tool, tool_input, pending=True)

    try:
        result = func(**tool_input)
        if session_id:
            _save_session_state(session_id, tool, tool_input, pending=False)
    except TypeError as exc:
        return {
            "error": "Invalid tool input",
            "details": str(exc),
            "tool": tool,
            "tool_input": tool_input,
            "plan_source": plan_source,
            "raw_model_output": model_output,
        }
    except Exception as exc:
        return {
            "error": "Error executing Bunq action",
            "details": str(exc),
            "tool": tool,
            "tool_input": tool_input,
            "plan_source": plan_source,
            "raw_model_output": model_output,
        }

    return _format_result(tool, result)


# ── Public API ────────────────────────────────────────────────────────────────

def run(audio_bytes: bytes, content_type: str = "audio/webm") -> str:
    """Full pipeline: audio → Nova Sonic STT → Bedrock Converse → bunq → result."""
    fmt        = content_type.split("/")[-1].split(";")[0]
    transcript = transcribe_with_nova_sonic(audio_bytes, media_format=fmt)
    return parse_and_execute(transcript)


def run_text(text: str, session_id: str | None = None) -> object:
    """Text-only pipeline (no STT): text → Bedrock text model → bunq → result."""
    return parse_and_execute(text, session_id)
