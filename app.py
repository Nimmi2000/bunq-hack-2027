"""
Streamlit frontend for the bunq Finn demo.

Starts the FastAPI voice backend (backend.py) as a daemon thread on port 8000,
then renders the phone-style UI via st.components.v1.html().

Voice pipeline (triggered by the 🎤 FAB):
  Web Speech API (browser STT) → POST /query → Amazon Bedrock (tool use)
  → bunq_functions.py → natural language reply → Web Speech TTS
"""

import socket
import threading

from dotenv import load_dotenv
load_dotenv()  # loads .env from the project root before anything else

import os
import streamlit as st
import streamlit.components.v1 as components
import uvicorn
from finn import backend

# ── Launch FastAPI backend once per process ───────────────────────────────────

BACKEND_PORT = int(os.environ.get("BACKEND_PORT", 8000))


def _backend_running() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("localhost", BACKEND_PORT)) == 0


def _start_backend() -> None:
    if not _backend_running():
        uvicorn.run(backend.app, host="0.0.0.0", port=BACKEND_PORT, log_level="error")


if "backend_thread_started" not in st.session_state:
    t = threading.Thread(target=_start_backend, daemon=True)
    t.start()
    st.session_state.backend_thread_started = True

# ── Streamlit page config ─────────────────────────────────────────────────────

st.set_page_config(
    page_title="bunq",
    page_icon="💜",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
    #MainMenu, footer, header { visibility: hidden; }
    [data-testid="stAppViewContainer"] { background: #0a0a0a !important; }
    [data-testid="stHeader"] { display: none !important; }
    [data-testid="block-container"] {
        padding: 0 !important;
        max-width: 430px !important;
        margin: 0 auto !important;
    }
    section[data-testid="stSidebar"] { display: none !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Full HTML/CSS/JS bundle rendered in an iframe ─────────────────────────────

HTML = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  background: #0a0a0a;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  color: #fff;
  min-height: 100vh;
  overflow-x: hidden;
}}

/* ── Phone shell ── */
.phone {{
  background: #0a0a0a;
  max-width: 390px;
  margin: 0 auto;
  min-height: 100vh;
  padding-bottom: 110px;
}}

/* ── Status bar ── */
.status-bar {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 22px 4px;
  font-size: 12px;
  font-weight: 600;
}}

/* ── Top bar ── */
.top-bar {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 20px 14px;
}}
.top-bar h1 {{
  font-size: 28px;
  font-weight: 800;
  letter-spacing: -.5px;
}}
.top-icons {{ display: flex; gap: 12px; }}
.icon-btn {{
  width: 36px; height: 36px;
  border-radius: 50%;
  background: #1e1e1e;
  display: flex; align-items: center; justify-content: center;
  font-size: 15px; cursor: pointer;
  border: none; color: #fff;
}}

/* ── Search bar ── */
.search-bar {{
  margin: 0 16px 18px;
  background: #1a1a1a;
  border-radius: 14px;
  padding: 13px 16px;
  display: flex; align-items: center; gap: 10px;
  cursor: pointer;
  border: 1px solid #252525;
}}
.search-star {{ color: #9d52f5; font-size: 14px; }}
.search-text {{ color: #666; font-size: 14px; }}

/* ── Section header ── */
.section-header {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 20px 12px;
  font-size: 16px;
  font-weight: 700;
}}
.section-header .chevron {{ color: #555; font-size: 20px; }}

/* ── Cards grid ── */
.cards-grid {{
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  padding: 0 16px;
  margin-bottom: 8px;
}}
.card {{
  border-radius: 20px;
  padding: 16px;
  min-height: 108px;
  position: relative;
  overflow: hidden;
}}

/* Balance card */
.card-balance {{
  background: linear-gradient(145deg, #6d28d9 0%, #8b5cf6 55%, #c084fc 100%);
}}
.card-balance .lbl {{
  font-size: 11px; font-weight: 500; opacity: .85;
  margin-bottom: 8px;
  display: flex; align-items: center; gap: 5px;
}}
.card-balance .amt {{ font-size: 23px; font-weight: 800; line-height: 1.1; }}
.card-balance .sub {{ font-size: 13px; font-weight: 500; opacity: .75; margin-top: 2px; }}

/* Vacay card */
.card-vacay {{ background: #181818; border: 1px solid #252525; }}
.card-vacay .ttl {{ font-size: 13px; font-weight: 700; margin-bottom: 14px; }}
.card-vacay .icons {{ display: flex; gap: 8px; font-size: 20px; }}

/* Main / Savings */
.card-main, .card-savings {{ background: #181818; border: 1px solid #252525; }}
.dot {{ width: 9px; height: 9px; border-radius: 50%; display: inline-block; margin-right: 6px; flex-shrink: 0; }}
.dot-orange {{ background: #f97316; }}
.dot-green  {{ background: #22c55e; }}
.card-ttl {{ font-size: 13px; font-weight: 700; margin-bottom: 8px; display: flex; align-items: center; }}
.card-amt {{ font-size: 20px; font-weight: 800; }}

/* Everyday full-width */
.card-everyday {{
  grid-column: span 2;
  background: linear-gradient(135deg, #1a1a2e 0%, #2d1b69 55%, #1a1a2e 100%);
  border: 1px solid #3a2a6a;
  min-height: 72px;
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 20px;
}}
.everyday-left .lbl {{ font-size: 11px; font-weight: 600; color: #999; margin-bottom: 4px; }}
.everyday-left .num {{ font-size: 15px; font-weight: 700; letter-spacing: 2px; }}
.mc {{ display: flex; align-items: center; }}
.mc-c {{ width: 28px; height: 28px; border-radius: 50%; }}
.mc-r {{ background: #eb001b; margin-right: -10px; z-index: 1; }}
.mc-o {{ background: #f79e1b; opacity: .9; }}

/* ── Quick actions ── */
.quick-actions {{
  display: flex; justify-content: center; gap: 48px;
  padding: 22px 16px 10px;
}}
.qbtn {{
  display: flex; flex-direction: column; align-items: center; gap: 8px;
  cursor: pointer; background: none; border: none; color: #fff;
}}
.qbtn-icon {{
  width: 52px; height: 52px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 20px; font-weight: 700;
}}
.qbtn-label {{ color: #777; font-size: 12px; font-weight: 500; }}
.ic-pay {{ background: linear-gradient(135deg,#f97316,#fb923c); }}
.ic-req {{ background: linear-gradient(135deg,#3b82f6,#60a5fa); }}
.ic-add {{ background: linear-gradient(135deg,#7c3aed,#a78bfa); }}

/* ── Bottom nav ── */
.bottom-nav {{
  position: fixed; bottom: 0; left: 50%;
  transform: translateX(-50%);
  width: 100%; max-width: 390px;
  background: #101010;
  border-top: 1px solid #1e1e1e;
  display: flex; justify-content: space-around;
  padding: 10px 0 22px;
  z-index: 100;
}}
.nav-item {{
  display: flex; flex-direction: column; align-items: center; gap: 3px;
  cursor: pointer; color: #444; font-size: 10px; font-weight: 500;
}}
.nav-item.active {{ color: #fff; }}
.nav-icon {{ font-size: 20px; }}
.nav-dot {{ width: 4px; height: 4px; border-radius: 50%; background: #7c3aed; margin: 0 auto; }}

/* ── Voice FAB ── */
#voice-fab {{
  position: fixed;
  bottom: 90px;
  right: max(12px, calc(50% - 195px + 12px));
  width: 52px; height: 52px;
  border-radius: 50%;
  background: linear-gradient(135deg,#7c3aed,#a78bfa);
  border: none; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  font-size: 22px;
  box-shadow: 0 4px 20px rgba(124,58,237,.55);
  z-index: 200;
  transition: transform .15s, box-shadow .15s;
}}
#voice-fab:hover {{ transform: scale(1.08); box-shadow: 0 6px 28px rgba(124,58,237,.75); }}
#voice-fab.recording {{
  background: linear-gradient(135deg,#dc2626,#f87171);
  animation: pulse 1.2s ease-in-out infinite;
}}
@keyframes pulse {{
  0%,100% {{ box-shadow: 0 4px 20px rgba(220,38,38,.5); transform: scale(1); }}
  50%      {{ box-shadow: 0 4px 32px rgba(220,38,38,.9); transform: scale(1.1); }}
}}

/* ── Voice modal ── */
#voice-modal {{
  display: none;
  position: fixed; inset: 0; z-index: 300;
  align-items: flex-end; justify-content: center;
  padding-bottom: 110px;
}}
#voice-modal.open {{ display: flex; }}
.modal-backdrop {{
  position: absolute; inset: 0;
  background: rgba(0,0,0,.55);
}}
.modal-sheet {{
  position: relative;
  width: calc(100% - 32px); max-width: 358px;
  background: #161616;
  border: 1px solid #2a2a2a;
  border-radius: 24px;
  padding: 20px; z-index: 1;
  box-shadow: 0 16px 60px rgba(0,0,0,.7);
}}
.modal-tag  {{ font-size: 10px; font-weight: 700; color: #a78bfa; letter-spacing: 1px; margin-bottom: 6px; }}
.modal-title {{ font-size: 17px; font-weight: 700; margin-bottom: 4px; }}
.modal-sub  {{ font-size: 12px; color: #666; margin-bottom: 16px; }}
.modal-close {{
  position: absolute; top: 14px; right: 16px;
  background: #252525; border: none; color: #aaa;
  width: 28px; height: 28px; border-radius: 50%;
  cursor: pointer; font-size: 14px;
  display: flex; align-items: center; justify-content: center;
}}
.modal-close:hover {{ color: #fff; background: #333; }}

/* Listening waveform */
#listening-indicator {{
  display: flex; align-items: flex-end; justify-content: center;
  gap: 5px; height: 52px; margin: 14px 0 10px;
}}
.wave-bar {{
  width: 4px; border-radius: 2px;
  background: linear-gradient(to top,#7c3aed,#c084fc);
  animation: wave 1.1s ease-in-out infinite;
}}
.wave-bar:nth-child(1) {{ animation-delay: 0s; }}
.wave-bar:nth-child(2) {{ animation-delay: 0.18s; }}
.wave-bar:nth-child(3) {{ animation-delay: 0.36s; }}
.wave-bar:nth-child(4) {{ animation-delay: 0.18s; }}
.wave-bar:nth-child(5) {{ animation-delay: 0s; }}
@keyframes wave {{
  0%,100% {{ height: 6px; opacity: .3; }}
  50%      {{ height: 40px; opacity: 1; }}
}}
#listening-indicator.idle .wave-bar {{
  animation: none; height: 4px; opacity: .15;
}}

/* Text input row */
.input-row {{ display: flex; gap: 8px; margin-top: 10px; margin-bottom: 6px; }}
.finn-input {{
  flex: 1;
  background: #1e1e1e; border: 1px solid #333;
  border-radius: 12px; padding: 10px 14px;
  color: #fff; font-size: 13px; outline: none;
}}
.finn-input::placeholder {{ color: #555; }}
.finn-input:focus {{ border-color: #7c3aed; }}
.send-btn {{
  background: linear-gradient(135deg,#7c3aed,#a78bfa);
  border: none; border-radius: 12px;
  padding: 10px 14px; color: #fff; font-size: 16px; cursor: pointer;
}}

/* Status / spinner */
#mic-status {{
  font-size: 11px; color: #555;
  text-align: center; margin-bottom: 6px; min-height: 16px;
}}
#mic-transcript {{
  font-size: 12px; color: #fff;
  text-align: center; min-height: 24px;
  padding: 6px 12px;
  background: rgba(255,255,255,0.03);
  border-radius: 10px;
  margin-bottom: 10px;
  word-break: break-word;
}}
.spinner {{
  display: none; text-align: center;
  color: #666; font-size: 12px; padding: 8px 0;
}}
.spinner.show {{ display: block; }}

/* Response bubble */
.finn-response {{
  background: #0d0d1a;
  border: 1px solid rgba(58,42,106,.4);
  border-radius: 14px; padding: 12px 14px;
  font-size: 13px; color: #ddd; line-height: 1.6;
  display: none;
}}
.finn-response.show {{ display: block; }}
.finn-name {{ color: #a78bfa; font-weight: 700; margin-bottom: 4px; font-size: 11px; letter-spacing: .5px; }}

/* Pipeline steps indicator */
.steps {{
  display: flex; gap: 6px; margin-bottom: 8px; flex-wrap: wrap;
}}
.step {{
  font-size: 10px; padding: 3px 8px;
  border-radius: 8px; background: #1e1e1e; color: #555;
  border: 1px solid #2a2a2a;
  transition: all .3s;
}}
.step.active  {{ background: #1a0f2e; color: #a78bfa; border-color: #7c3aed44; }}
.step.done    {{ background: #0a1a0a; color: #22c55e; border-color: #22c55e44; }}
.step.error   {{ background: #1a0a0a; color: #f87171; border-color: #dc262644; }}

/* ── Face ID setup modal ── */
#face-setup-modal {{
  display: none;
  position: fixed; inset: 0; z-index: 400;
  align-items: center; justify-content: center;
  padding: 16px;
}}
#face-setup-modal.open {{ display: flex; }}
.face-sheet {{
  position: relative;
  width: 100%; max-width: 358px;
  background: #161616;
  border: 1px solid #3a2a6a;
  border-radius: 24px;
  padding: 20px; z-index: 1;
  box-shadow: 0 16px 60px rgba(0,0,0,.9);
}}
#setup-video {{
  width: 100%;
  border-radius: 14px;
  background: #0a0a0a;
  min-height: 200px;
  margin-bottom: 14px;
  border: 2px solid #3a2a6a;
  object-fit: cover;
}}
.face-capture-btn {{
  width: 100%;
  background: linear-gradient(135deg,#7c3aed,#a78bfa);
  border: none; border-radius: 12px;
  color: #fff; padding: 13px 16px;
  font-size: 14px; font-weight: 700;
  cursor: pointer; margin-bottom: 10px;
  transition: opacity .15s;
}}
.face-capture-btn:hover {{ opacity: .88; }}
#setup-status {{
  font-size: 12px; color: #888;
  text-align: center; min-height: 18px;
  padding: 2px 0;
}}
</style>
</head>
<body>

<div class="phone">

  <!-- Status bar -->
  <div class="status-bar">
    <span>10:10</span>
    <div style="display:flex;gap:8px;align-items:center;">
      <span>&#9646;&#9646;&#9646;</span>
      <span>&#x1F4F6;</span>
      <span>&#x1F50B;</span>
    </div>
  </div>

  <!-- Top bar -->
  <div class="top-bar">
    <h1>Home</h1>
    <div class="top-icons">
      <button class="icon-btn">&#x1F514;</button>
      <button class="icon-btn">&#x229E;</button>
    </div>
  </div>

  <!-- Ask Finn -->
  <div class="search-bar" onclick="openVoice()">
    <span class="search-star">&#x2736;</span>
    <span class="search-text">Ask Finn Anything</span>
  </div>

  <!-- Section: Eva -->
  <div class="section-header">
    <span>Eva</span>
    <span class="chevron">&#x203A;</span>
  </div>

  <!-- Cards grid -->
  <div class="cards-grid">

    <div class="card card-balance">
      <div class="lbl"><span>&#x2736;</span> Total balance</div>
      <div class="amt">&euro; 2,433</div>
      <div class="sub">.00</div>
    </div>

    <div class="card card-vacay">
      <div class="ttl">Summer Vacay</div>
      <div class="icons">&#x2708;&#xFE0F; &#x1F3CA; &#x1F381;</div>
    </div>

    <div class="card card-main">
      <div class="card-ttl"><span class="dot dot-orange"></span>Main</div>
      <div class="card-amt">&euro; 900.00</div>
    </div>

    <div class="card card-savings">
      <div class="card-ttl"><span class="dot dot-green"></span>Savings</div>
      <div class="card-amt">&euro; 310.00</div>
    </div>

    <div class="card card-everyday">
      <div class="everyday-left">
        <div class="lbl">Everyday</div>
        <div class="num">&#x2022;&#x2022;&#x2022;&#x2022; 1234 &nbsp; 125</div>
      </div>
      <div class="mc">
        <div class="mc-c mc-r"></div>
        <div class="mc-c mc-o"></div>
      </div>
    </div>

  </div>

  <!-- Quick actions -->
  <div class="quick-actions">
    <button class="qbtn"><div class="qbtn-icon ic-pay">&#x2191;</div><span class="qbtn-label">Pay</span></button>
    <button class="qbtn"><div class="qbtn-icon ic-req">&#x2193;</div><span class="qbtn-label">Request</span></button>
    <button class="qbtn"><div class="qbtn-icon ic-add">&#xFF0B;</div><span class="qbtn-label">Add</span></button>
  </div>

</div><!-- /phone -->

<!-- Bottom nav -->
<div class="bottom-nav">
  <div class="nav-item active"><div class="nav-icon">&#x1F3E0;</div><span>Home</span><div class="nav-dot"></div></div>
  <div class="nav-item"><div class="nav-icon">&#x2708;&#xFE0F;</div><span>Travel</span></div>
  <div class="nav-item"><div class="nav-icon">&#x1F4CA;</div><span>Budgeting</span></div>
  <div class="nav-item"><div class="nav-icon">&#x1F4C8;</div><span>Stocks</span></div>
  <div class="nav-item"><div class="nav-icon">&#x20BF;</div><span>Crypto</span></div>
</div>

<!-- Voice FAB -->
<button id="voice-fab" title="Ask Finn" onclick="openVoice()">&#x1F3A4;</button>

<!-- Voice modal -->
<div id="voice-modal">
  <div class="modal-backdrop" onclick="closeVoice()"></div>
  <div class="modal-sheet">
    <button class="modal-close" onclick="closeVoice()">&#x2715;</button>
    <div class="modal-tag">&#x2736; FINN VOICE</div>
    <div class="modal-title">Ask Finn</div>
    <div class="modal-sub">Speak your banking command.</div>

    <!-- Pipeline steps -->
    <div class="steps">
      <span class="step" id="step-face">&#x1F512; Face ID</span>
      <span class="step" id="step-mic">&#x1F3A4; Voice</span>
      <span class="step" id="step-bedrock">&#x1F916; Bedrock</span>
      <span class="step" id="step-bunq">&#x1F3E6; bunq</span>
    </div>

    <!-- Live listening waveform -->
    <div id="listening-indicator" class="idle">
      <div class="wave-bar"></div>
      <div class="wave-bar"></div>
      <div class="wave-bar"></div>
      <div class="wave-bar"></div>
      <div class="wave-bar"></div>
    </div>
    <div id="mic-status"></div>

    <!-- Text input -->
    <div class="input-row">
      <input
        class="finn-input" id="finn-input" type="text"
        placeholder="Or type a command&#x2026;"
        onkeydown="if(event.key==='Enter') askFinnText()"
      >
      <button class="send-btn" onclick="askFinnText()">&#x279C;</button>
    </div>

    <div class="spinner" id="spinner">Processing&#x2026;</div>

    <div class="finn-response" id="finn-response">
      <div class="finn-name">FINN</div>
      <div id="finn-text"></div>
    </div>
  </div>
</div>

<!-- Face ID Setup Modal -->
<div id="face-setup-modal">
  <div class="modal-backdrop"></div>
  <div class="face-sheet">
    <div class="modal-tag">&#x1F512; FACE ID SETUP</div>
    <div class="modal-title">Set Up Face ID</div>
    <div class="modal-sub">Capture your face to secure bunq banking actions.</div>
    <video id="setup-video" autoplay playsinline muted></video>
    <canvas id="setup-canvas" style="display:none;"></canvas>
    <button class="face-capture-btn" onclick="captureSetupFace()">&#x1F4F7;&nbsp; Capture Reference Photo</button>
    <div id="setup-status"></div>
  </div>
</div>

<script>
function getBackendOrigin() {{
  let origin = '';
  try {{
    if (window.parent && window.parent.location && window.parent.location.origin && window.parent.location.origin.startsWith('http')) {{
      origin = window.parent.location.origin;
    }}
  }} catch (e) {{}}
  if (!origin) {{
    try {{
      if (document.referrer) {{
        const ref = new URL(document.referrer);
        if (ref.origin.startsWith('http')) origin = ref.origin;
      }}
    }} catch (e) {{}}
  }}
  if (!origin && window.location.origin && window.location.origin.startsWith('http')) {{
    origin = window.location.origin;
  }}
  if (!origin) {{
    const protocol = window.location.protocol && window.location.protocol.startsWith('http')
      ? window.location.protocol
      : 'http:';
    const hostname = window.location.hostname || 'localhost';
    origin = protocol + '//' + hostname;
  }}

  try {{
    const parsed = new URL(origin);
    parsed.port = '{BACKEND_PORT}';
    return parsed.origin;
  }} catch (e) {{
    return origin.replace(/:\\d+$/, '') + ':{BACKEND_PORT}';
  }}
}}
const BACKEND = getBackendOrigin();
const SESSION_ID_KEY = 'finnSessionId';
let SESSION_ID = localStorage.getItem(SESSION_ID_KEY);
if (!SESSION_ID) {{
  SESSION_ID = (crypto.randomUUID ? crypto.randomUUID() : 'finn-' + Math.random().toString(36).slice(2));
  localStorage.setItem(SESSION_ID_KEY, SESSION_ID);
}}
console.log('Finn BACKEND endpoint:', BACKEND, 'session:', SESSION_ID);

// ── Pipeline step indicator helpers ──────────────────────────────────────────
const STEPS = ['step-face','step-mic','step-bedrock','step-bunq'];
function setStep(id, state) {{
  const el = document.getElementById(id);
  if (el) el.className = 'step ' + state;
}}
function resetSteps() {{
  STEPS.forEach(s => {{
    const el = document.getElementById(s);
    if (el) el.className = 'step';
  }});
}}
function allStepsDone() {{
  STEPS.forEach(s => {{
    const el = document.getElementById(s);
    if (el) el.className = 'step done';
  }});
}}

// ── Modal open/close ──────────────────────────────────────────────────────────
function openVoice() {{
  stopWakeListener();
  document.getElementById('voice-modal').classList.add('open');
  resetSteps();
  if (!isListening) startListening();
}}
function closeVoice() {{
  stopListening();
  document.getElementById('voice-modal').classList.remove('open');
  startWakeListener();
}}

// ── Show response + TTS ───────────────────────────────────────────────────────
function showResponse(text) {{
  document.getElementById('spinner').classList.remove('show');
  let display = text;
  if (typeof text === 'object' && text !== null) {{
    if (text.message) display = text.message;
    else display = JSON.stringify(text, null, 2);
  }}
  document.getElementById('finn-text').textContent = display;
  document.getElementById('finn-response').classList.add('show');
  document.getElementById('mic-status').textContent = '';
  allStepsDone();
  speak(display);
}}

function showError(msg) {{
  document.getElementById('spinner').classList.remove('show');
  document.getElementById('finn-text').textContent = '⚠️ ' + msg;
  document.getElementById('finn-response').classList.add('show');
  STEPS.forEach(s => {{
    const el = document.getElementById(s);
    if (el && el.className.includes('active')) el.className = 'step error';
  }});
}}

function speak(text) {{
  if (!window.speechSynthesis) return;
  window.speechSynthesis.cancel();
  const utt = new SpeechSynthesisUtterance(text);
  utt.rate = 1.0; utt.pitch = 1.05;
  const voices = window.speechSynthesis.getVoices();
  const v = voices.find(v =>
    v.name.includes('Samantha') ||
    v.name.toLowerCase().includes('female') ||
    (v.lang === 'en-US' && v.name.includes('Google'))
  );
  if (v) utt.voice = v;
  window.speechSynthesis.speak(utt);
}}
window.speechSynthesis && window.speechSynthesis.getVoices();

// ── Face authentication ────────────────────────────────────────────────────────
let setupStream = null;

async function openFaceSetup() {{
  document.getElementById('face-setup-modal').classList.add('open');
  document.getElementById('setup-status').textContent = 'Starting camera…';
  try {{
    setupStream = await navigator.mediaDevices.getUserMedia({{video: {{facingMode: 'user'}}}});
    const video = document.getElementById('setup-video');
    video.srcObject = setupStream;
    await video.play();
    document.getElementById('setup-status').textContent = '';
  }} catch(e) {{
    document.getElementById('setup-status').textContent = 'Camera access denied — allow camera in browser settings.';
  }}
}}

async function captureSetupFace() {{
  const video = document.getElementById('setup-video');
  if (!video.videoWidth) {{
    document.getElementById('setup-status').textContent = 'Camera not ready — please wait.';
    return;
  }}
  const canvas = document.getElementById('setup-canvas');
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  canvas.getContext('2d').drawImage(video, 0, 0);
  const b64 = canvas.toDataURL('image/jpeg', 0.9).split(',')[1];
  document.getElementById('setup-status').textContent = 'Saving reference photo…';
  try {{
    const res = await fetch(BACKEND + '/face/setup', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{image: b64}})
    }});
    const data = await res.json();
    if (data.status === 'ok') {{
      if (setupStream) setupStream.getTracks().forEach(t => t.stop());
      setupStream = null;
      document.getElementById('face-setup-modal').classList.remove('open');
      document.getElementById('setup-status').textContent = '';
      openVoice();
    }} else {{
      document.getElementById('setup-status').textContent = 'Setup failed: ' + (data.error || 'unknown error');
    }}
  }} catch(e) {{
    document.getElementById('setup-status').textContent = 'Network error: ' + e.message;
  }}
}}

async function captureAndVerifyFace() {{
  let stream = null;
  try {{
    stream = await navigator.mediaDevices.getUserMedia({{video: {{facingMode: 'user', width: 640, height: 480}}}});
    const video = document.createElement('video');
    video.srcObject = stream;
    video.muted = true;
    video.playsInline = true;
    await new Promise(resolve => {{ video.onloadedmetadata = resolve; setTimeout(() => resolve(), 2000); }});
    await video.play();
    await new Promise(r => setTimeout(r, 400));
    const canvas = document.createElement('canvas');
    canvas.width = video.videoWidth || 640;
    canvas.height = video.videoHeight || 480;
    canvas.getContext('2d').drawImage(video, 0, 0);
    const b64 = canvas.toDataURL('image/jpeg', 0.85).split(',')[1];
    const vRes = await fetch(BACKEND + '/face/verify', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{image: b64}})
    }});
    const vData = await vRes.json();
    return vData.match === true;
  }} catch(e) {{
    console.warn('Face verify error:', e);
    return false;
  }} finally {{
    if (stream) stream.getTracks().forEach(t => t.stop());
  }}
}}

// ── Wake-word listener (background, always-on) ───────────────────────────────
let wakeRecognition = null;
let wakeListening   = false;

function startWakeListener() {{
  if (!SpeechRecognition || wakeListening) return;
  wakeListening   = true;
  wakeRecognition = new SpeechRecognition();
  wakeRecognition.continuous    = true;
  wakeRecognition.interimResults = false;
  wakeRecognition.lang          = 'en-US';

  wakeRecognition.onresult = event => {{
    for (let i = event.resultIndex; i < event.results.length; i++) {{
      if (!event.results[i].isFinal) continue;
      const phrase = event.results[i][0].transcript.toLowerCase().trim();
      if (phrase.includes('open voice') || phrase.includes('open finn') || phrase.includes('hey finn')) {{
        openVoice();
      }}
    }}
  }};

  wakeRecognition.onend = () => {{
    if (wakeListening) {{
      setTimeout(() => {{ try {{ wakeRecognition.start(); }} catch(e) {{}} }}, 300);
    }}
  }};

  wakeRecognition.onerror = () => {{}};
  try {{ wakeRecognition.start(); }} catch(e) {{}}
}}

function stopWakeListener() {{
  wakeListening = false;
  if (wakeRecognition) {{
    try {{ wakeRecognition.stop(); }} catch(e) {{}}
    wakeRecognition = null;
  }}
}}

async function checkFaceSetupAndInit() {{
  try {{
    const res = await fetch(BACKEND + '/face/status');
    const data = await res.json();
    if (!data.reference_set) {{
      await openFaceSetup();
    }} else {{
      startWakeListener();
    }}
  }} catch(e) {{
    startWakeListener();
  }}
}}

window.addEventListener('load', () => {{ setTimeout(() => checkFaceSetupAndInit(), 1000); }});

// ── Text input → /query endpoint ─────────────────────────────────────────────
async function askFinnText() {{
  const input = document.getElementById('finn-input');
  const text = input.value.trim();
  if (!text) return;
  input.value = '';
  await sendTextToBackend(text);
}}

// ── Browser speech recognition → /query endpoint ────────────────────────────
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

let recognition = null;
let isListening = false;
let stopRequested = false;
let accumulatedTranscript = '';

function toggleListening() {{
  if (isListening) stopListening();
  else             startListening();
}}

function startListening() {{
  if (!SpeechRecognition) {{
    showError('Speech recognition is not supported in this browser.');
    return;
  }}

  if (isListening) return;

  stopRequested = false;
  accumulatedTranscript = '';
  recognition = new SpeechRecognition();
  recognition.continuous = true;
  recognition.interimResults = true;
  recognition.maxAlternatives = 1;
  recognition.lang = 'en-US';

  recognition.onstart = () => {{
    isListening = true;
    setStep('step-mic', 'active');
    document.getElementById('voice-fab').classList.add('recording');
    document.getElementById('listening-indicator').classList.remove('idle');
    document.getElementById('mic-status').textContent = '';
    document.getElementById('finn-response').classList.remove('show');
  }};

  recognition.onresult = async event => {{
    let interimTranscript = '';
    for (let i = event.resultIndex; i < event.results.length; i++) {{
      const resultText = event.results[i][0].transcript;
      if (event.results[i].isFinal) {{
        accumulatedTranscript += resultText + ' ';
        const fullText = accumulatedTranscript.trim();
        const lower = fullText.toLowerCase();
        if (lower.includes('i am done') || lower.includes("i'm done") || lower.includes('im done') || lower.includes('i am finished') || lower.includes('i m done') || lower.includes('close voice') || lower.includes('close finn')) {{
          closeVoice();
          return;
        }}
        if (fullText) {{
          accumulatedTranscript = '';
          await sendTextToBackend(fullText);
        }}
      }} else {{
        interimTranscript += resultText + ' ';
      }}
    }}
  }};

  recognition.onerror = event => {{
    if (event.error === 'no-speech' || event.error === 'aborted') {{
      document.getElementById('mic-status').textContent = 'No speech detected. Keep talking or tap stop and try again.';
    }} else if (event.error === 'network') {{
      showError('Speech recognition network error. Retrying...');
    }} else {{
      showError(event.error || 'Speech recognition failed.');
      stopRequested = true;
    }}
  }};

  recognition.onend = () => {{
    if (stopRequested) {{
      isListening = false;
      document.getElementById('voice-fab').classList.remove('recording');
      document.getElementById('listening-indicator').classList.add('idle');
      recognition = null;
      return;
    }}

    if (isListening) {{
      setTimeout(() => {{
        try {{
          recognition.start();
        }} catch (e) {{
          console.warn('Speech recognition restart failed:', e);
          showError('Speech recognition stopped unexpectedly.');
        }}
      }}, 250);
    }}
  }};

  try {{
    recognition.start();
  }} catch (e) {{
    showError('Speech recognition unavailable.');
  }}
}}

function stopListening() {{
  if (recognition && isListening) {{
    stopRequested = true;
    recognition.stop();
  }} else {{
    document.getElementById('voice-fab').classList.remove('recording');
    document.getElementById('listening-indicator').classList.add('idle');
  }}
}}

async function sendTextToBackend(text) {{
  resetSteps();
  document.getElementById('finn-response').classList.remove('show');
  document.getElementById('spinner').classList.add('show');
  setStep('step-face', 'active');
  document.getElementById('mic-status').textContent = 'Verifying identity…';

  let faceOk = false;
  try {{ faceOk = await captureAndVerifyFace(); }} catch(e) {{ faceOk = false; }}

  if (!faceOk) {{
    document.getElementById('spinner').classList.remove('show');
    setStep('step-face', 'error');
    document.getElementById('finn-text').textContent = '⚠️ Face not recognised — look directly at the camera and try again.';
    document.getElementById('finn-response').classList.add('show');
    document.getElementById('mic-status').textContent = '';
    return;
  }}

  setStep('step-face', 'done');
  setStep('step-bedrock', 'active');
  document.getElementById('mic-status').textContent = '';

  const endpoint = BACKEND + '/query';
  try {{
    console.log('Fetch backend endpoint', endpoint);
    const res = await fetch(endpoint, {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{ text, session_id: SESSION_ID, face_verified: true }})
    }});
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Backend error');

    setStep('step-bedrock', 'done');
    setStep('step-bunq', 'active');
    document.getElementById('mic-status').textContent = 'Executing bunq action…';
    await new Promise(r => setTimeout(r, 400));

    showResponse(data.response);
  }} catch(e) {{
    showError(e.message + ' — ' + endpoint);
  }}
}}
</script>

</body>
</html>"""

components.html(HTML, height=820, scrolling=False)
