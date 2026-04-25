# Finn 2.0 — AI-Driven Safe Transaction System

Finn 2.0 is not a voice banking app. It is an **AI-powered transaction protection layer** built on top of bunq that detects fraud, coercion, and identity risk in real time — before a transaction happens.

Built for the **bunq Hackathon 2027**.

---

## The Problem

Voice banking and accessibility features are useful, but they solve the wrong problem. The real risk in digital banking is not *how* users interact — it is *whether they are safe when they do*.

- Elderly and vulnerable users are targeted by scammers who walk them through forced transfers
- Authorised push payment (APP) fraud is the fastest-growing fraud category in Europe
- Standard authentication (PIN, face ID) confirms identity but cannot detect coercion or manipulation
- Banks have no signal to distinguish a genuine payment from one made under pressure

**Judges will ask: "Why does this need AI?"**
The answer: only AI can listen to voice, read context, analyse behaviour, and make a risk decision in real time.

---

## What Finn 2.0 Does

Finn 2.0 intercepts every transaction and makes an **AI risk decision** before it executes.

```
User speaks a request
        │
        ▼
STT Transcription      ◄── Web Speech API / Amazon Nova Sonic
        │
        ▼
Intent Recognition     ◄── Amazon Bedrock Nova Pro (LLM)
        │                    extracts: action, amount, recipient
        ▼
Face Verification      ◄── live webcam capture
        │              ◄── compared to stored reference image
        │              ◄── Amazon Bedrock Nova Lite (vision model)
        ▼
  ALLOW / BLOCK
        │
        ├─ ALLOW  → execute bunq API action
        │              ├─ make payment
        │              ├─ request money
        │              ├─ create payment link
        │              ├─ list accounts & balances
        │              └─ list transactions
        └─ BLOCK  → reject, prompt user to retry face check
```

This is the core product. Voice interaction and face verification are delivery mechanisms — **AI risk detection is the value**.

---

## Core Capabilities

### 1. Voice-to-Intent Pipeline
Speech is captured in the browser and streamed to Amazon Nova Sonic for transcription. The transcript is sent to an Amazon Bedrock LLM that identifies the user's intent (payment, balance check, money request, payment link) and routes it to the correct bunq API action.

### 2. Banking Actions via bunq API
The system executes real bunq API calls:
- **Make a payment** — send money to a contact by name or email
- **List accounts & balances** — retrieve account summary
- **Request money** — create an inbound payment request
- **Create a payment link** — generate a shareable bunq.me link

### 3. Face Verification
Before any transaction executes, the user must pass a face check. A live camera capture is compared against a stored reference image using Amazon Bedrock Nova Lite (vision model). The transaction proceeds only if the faces match.

### 4. Conversational Session Memory
The assistant maintains context across turns within a session, so follow-up instructions ("send the same amount to John instead") resolve correctly without the user repeating details.

---

## Compliance (GDPR-First Design)

| Principle | Implementation |
|---|---|
| No raw audio stored | Voice is processed in memory and discarded immediately |
| User consent | Risk analysis is disclosed upfront; user controls the session |
| Human override | AI assists, user has final say on all decisions |
| Step-up only | Biometric check triggered by risk, not applied continuously |
| Minimal data | Only transaction metadata and risk scores are retained |

---

## Demo Scenario

> Eva, 72, receives a call from a "bank employee" who asks her to transfer €3,000 to a "safe account". She opens Finn 2.0 and starts speaking the transfer request.

1. Finn 2.0 detects **elevated stress** in Eva's voice.
2. Finn 2.0 detects a **secondary voice** in the background.
3. The recipient is **new** and the amount is **10× her usual transfer**.
4. Risk score: **HIGH** → transaction is **blocked**.
5. Finn 2.0 says: *"I've paused this transfer. Are you being asked to do this by someone else? You can say 'cancel' or call your bank directly."*

This is the scenario that wins the hackathon. One clear problem, one clear AI solution.

---

## Architecture

```
app.py                          ← Streamlit phone UI (entry point)
finn/
  backend.py                    ← FastAPI server (port 8000)
  core/
    voice_pipeline.py           ← Intent recognition + risk-aware execution
    face_auth.py                ← Step-up biometric (triggered by risk score)
  integrations/
    bunq/
      client.py                 ← bunq REST client (auth + request signing)
      functions.py              ← Banking actions (make_payment, list_accounts, etc.)
examples/                       ← Standalone bunq API tutorial scripts
docs/                           ← API reference and troubleshooting
```

---

## Tech Stack

| | |
|---|---|
| Frontend | Streamlit + HTML/CSS/JS phone UI |
| Backend | FastAPI + Uvicorn |
| LLM / Risk AI | Amazon Bedrock — Nova Pro (`amazon.nova-pro-v1:0`) |
| Face step-up | Amazon Bedrock — Nova Lite vision (`amazon.nova-lite-v1:0`) |
| Voice input | Browser Web Speech API (Nova Sonic for deeper audio analysis) |
| Banking | bunq REST API (sandbox + production) |
| Language | Python 3.12, uv |

---

## Setup

```bash
git clone https://github.com/your-org/bunq-hack-2027.git
cd bunq-hack-2027
uv sync
cp .env.example .env   # add your credentials
uv run streamlit run app.py
```

Frontend: **http://localhost:8501** — Backend API docs: **http://localhost:8000/docs**

### Key Environment Variables

| Variable | Required | Description |
|---|---|---|
| `AWS_BEDROCK_API_KEY` | Yes | Bearer token for Bedrock (LLM + vision) |
| `AWS_REGION` | Yes | AWS region (e.g. `us-east-1`) |
| `BUNQ_API_KEY` | No | bunq key — auto-creates sandbox user if blank |
| `BUNQ_SANDBOX` | No | `true` for sandbox (default), `false` for production |
| `BEDROCK_MODEL_ID` | No | LLM model (default: `amazon.nova-pro-v1:0`) |
| `FACE_MODEL_ID` | No | Vision model (default: `amazon.nova-lite-v1:0`) |

---

## Why This Wins

| Criterion | How Finn 2.0 meets it |
|---|---|
| **Real problem** | APP fraud and elder scam coercion — billions lost annually across Europe |
| **AI is core** | Without the risk engine, there is no product — AI is not a feature, it is the system |
| **Non-text modality** | Voice tone, stress patterns, speaker count, and facial step-up all feed the decision |
| **Privacy-compliant** | GDPR-first: no raw data stored, consent-driven, biometrics on demand only |
| **bunq integration** | Risk engine gates real bunq API transactions — not a mock demo |

---

## Resources

- [bunq API Docs](https://doc.bunq.com) · [Amazon Bedrock](https://docs.aws.amazon.com/bedrock/) · [FastAPI](https://fastapi.tiangolo.com)
- [`docs/API_REFERENCE.md`](docs/API_REFERENCE.md) — bunq endpoint reference
- [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md) — common errors and fixes
