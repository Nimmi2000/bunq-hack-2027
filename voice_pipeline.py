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

AWS_REGION   = os.environ.get("AWS_REGION", "us-east-1")
STT_MODEL_ID = os.environ.get("BEDROCK_STT_MODEL_ID", "amazon.nova-sonic-v1:0")
MODEL_ID     = os.environ.get("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0")
BEDROCK_KEY  = os.environ.get("AWS_BEDROCK_API_KEY", "").strip().strip('"')

SYSTEM_PROMPT = (
    "You are Finn, bunq's friendly AI banking assistant. The user's name is Eva. "
    "Use the provided tools to fulfil banking requests precisely. "
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
                    "required": ["amount", "currency", "recipient_email", "description"],
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
                    "required": ["amount", "currency", "counterparty_email", "description"],
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


# ── Step 2+3: Bedrock Converse with tool use ──────────────────────────────────

def _converse(messages: list, tools: list | None = None) -> dict:
    """Call Bedrock Converse API using bearer token."""
    if not BEDROCK_KEY:
        raise EnvironmentError("AWS_BEDROCK_API_KEY is required.")

    payload: dict = {
        "system":          [{"text": SYSTEM_PROMPT}],
        "messages":        messages,
        "inferenceConfig": {"maxTokens": 1024},
    }
    if tools:
        payload["toolConfig"] = {"tools": tools}

    endpoint = (
        f"https://bedrock-runtime.{AWS_REGION}.amazonaws.com"
        f"/model/{urllib.parse.quote(MODEL_ID, safe='')}/converse"
    )
    headers = {
        "Authorization": f"Bearer {BEDROCK_KEY}",
        "Content-Type":  "application/json",
        "Accept":        "application/json",
    }
    resp = _http.post(endpoint, json=payload, headers=headers, timeout=60)
    resp.raise_for_status()
    return resp.json()


def parse_and_execute(transcript: str) -> str:
    """
    Turn 1 — send transcript to Bedrock; model selects a tool or responds directly.
    Execution — call the matching bunq function.
    Turn 2 — send tool result back; model returns a natural language reply.
    """
    messages: list[dict] = [
        {"role": "user", "content": [{"text": transcript}]}
    ]

    # ── Turn 1: intent detection ──────────────────────────────────────────────
    response1     = _converse(messages, tools=TOOLS)
    assistant_msg = response1["output"]["message"]
    messages.append(assistant_msg)

    if response1["stopReason"] != "tool_use":
        return next(
            (b["text"] for b in assistant_msg["content"] if "text" in b),
            "I'm not sure how to help with that.",
        )

    # ── Execute each requested tool ───────────────────────────────────────────
    tool_results: list[dict] = []
    for block in assistant_msg["content"]:
        if "toolUse" not in block:
            continue
        tool = block["toolUse"]
        func = FUNCTION_MAP.get(tool["name"])
        if func is None:
            result_text = f"Unknown function '{tool['name']}'"
        else:
            try:
                result_text = json.dumps(func(**tool["input"]), ensure_ascii=False)
            except Exception as exc:
                result_text = f"Error in {tool['name']}: {exc}"

        tool_results.append({
            "toolResult": {
                "toolUseId": tool["toolUseId"],
                "content":   [{"text": result_text}],
            }
        })

    messages.append({"role": "user", "content": tool_results})

    # ── Turn 2: natural language summary ──────────────────────────────────────
    response2 = _converse(messages, tools=TOOLS)
    return next(
        (b["text"] for b in response2["output"]["message"]["content"] if "text" in b),
        "Done.",
    )


# ── Public API ────────────────────────────────────────────────────────────────

def run(audio_bytes: bytes, content_type: str = "audio/webm") -> str:
    """Full pipeline: audio → Nova Sonic STT → Bedrock Converse → bunq → result."""
    fmt        = content_type.split("/")[-1].split(";")[0]
    transcript = transcribe_with_nova_sonic(audio_bytes, media_format=fmt)
    return parse_and_execute(transcript)


def run_text(text: str) -> str:
    """Text-only pipeline (no STT): text → Bedrock Converse → bunq → result."""
    return parse_and_execute(text)
