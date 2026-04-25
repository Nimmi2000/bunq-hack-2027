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
import backend

# ── Launch FastAPI backend once per process ───────────────────────────────────

BACKEND_PORT = int(os.environ.get("BACKEND_PORT", 8000))


def _backend_running() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("localhost", BACKEND_PORT)) == 0


def _start_backend() -> None:
    if not _backend_running():
        try:
            uvicorn.run(backend.app, host="0.0.0.0", port=BACKEND_PORT, log_level="info")
        except Exception as exc:
            import traceback
            print(f"[Finn] Backend failed to start: {exc}")
            traceback.print_exc()


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

/* Mic button */
.mic-btn {{
  width: 100%;
  background: #1e1e1e;
  border: 1px solid #2a2a2a;
  border-radius: 12px; color: #aaa;
  padding: 12px; font-size: 14px; font-weight: 600;
  cursor: pointer;
  display: flex; align-items: center; justify-content: center; gap: 10px;
  margin-bottom: 10px; transition: background .15s, border-color .15s;
}}
.mic-btn:hover {{ background: #222; }}
.mic-btn.recording {{
  background: #1a0808; border-color: #dc2626; color: #f87171;
  animation: pulse-border 1.2s ease-in-out infinite;
}}
@keyframes pulse-border {{
  0%,100% {{ box-shadow: 0 0 0 0 rgba(220,38,38,.4); }}
  50%      {{ box-shadow: 0 0 0 6px rgba(220,38,38,0); }}
}}

/* Text input row */
.input-row {{ display: flex; gap: 8px; margin-top: 10px; margin-bottom: 10px; }}
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

/* ── Camera preview ── */
#camera-section {{
  display: none;
  margin-bottom: 8px;
  border-radius: 10px;
  overflow: hidden;
  border: 1px solid #2a2a2a;
  position: relative;
}}
#camera-preview {{
  width: 100%; height: 80px;
  object-fit: cover; display: block;
  background: #111;
}}
.cam-badge {{
  position: absolute; bottom: 4px; right: 6px;
  font-size: 9px; background: rgba(0,0,0,.75);
  color: #22c55e; padding: 2px 6px; border-radius: 4px;
  font-weight: 700; letter-spacing: .5px;
}}

/* ── Risk analysis debug panel ── */
#risk-panel {{
  margin-top: 8px;
  background: #0e0e1a;
  border: 1px solid #2a2a4a;
  border-radius: 12px;
  padding: 10px 12px;
  display: none;
}}
.risk-header {{ font-size: 10px; font-weight: 700; color: #a78bfa; letter-spacing: 1px; margin-bottom: 6px; }}
.risk-bar-wrap {{ background: #1e1e1e; border-radius: 6px; height: 8px; overflow: hidden; margin-bottom: 6px; }}
#risk-bar {{ height: 100%; width: 0%; border-radius: 6px; transition: width .5s, background .5s; }}
.risk-meta {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }}
#risk-rec {{ font-size: 11px; font-weight: 700; letter-spacing: .5px; }}
#risk-score-text {{ font-size: 11px; color: #666; }}
#risk-reason {{ font-size: 11px; color: #888; margin-bottom: 6px; line-height: 1.4; }}
.risk-toggle-btn {{
  font-size: 10px; color: #555; cursor: pointer;
  background: none; border: none; padding: 0;
  text-decoration: underline; display: block; margin-bottom: 4px;
}}
#risk-details-body {{
  display: none; margin-top: 4px;
  font-size: 10px; color: #666; line-height: 1.7;
  font-family: 'Courier New', monospace;
  white-space: pre-wrap; word-break: break-all;
}}

/* ── Floating fraud panel (always visible, outside modal) ── */
#risk-float {{
  position: fixed; top: 16px; right: 16px;
  width: 260px;
  background: #0e0e1a;
  border: 1px solid #3a2a6a;
  border-radius: 14px;
  padding: 12px 14px;
  display: none; z-index: 400;
  box-shadow: 0 8px 30px rgba(0,0,0,.75);
}}
#risk-float .rf-header {{ font-size: 10px; font-weight: 700; color: #a78bfa; letter-spacing: 1px; margin-bottom: 6px; }}
#risk-float .rf-bar-wrap {{ background: #1a1a1a; border-radius: 6px; height: 8px; overflow: hidden; margin-bottom: 6px; }}
#risk-float-bar {{ height: 100%; width: 0%; border-radius: 6px; transition: width .5s, background .5s; }}
#risk-float .rf-meta {{ display: flex; justify-content: space-between; margin-bottom: 4px; }}
#risk-float-rec {{ font-size: 14px; font-weight: 800; }}
#risk-float-score {{ font-size: 11px; color: #666; }}
#risk-float-reason {{ font-size: 11px; color: #aaa; line-height: 1.5; margin-bottom: 6px; }}
#risk-float-signals {{ font-size: 10px; color: #666; font-family: monospace; white-space: pre-wrap; display: none; }}
.rf-toggle {{ font-size: 10px; color: #555; cursor: pointer; background: none; border: none; padding: 0; text-decoration: underline; }}
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
    <div class="modal-sub">Tap the mic and speak, or type your request.</div>
    <div id="backend-status" style="font-size:10px;color:#555;margin-bottom:6px;">Connecting to backend&#x2026;</div>

    <!-- Camera preview — inline in modal, hidden until camera is active -->
    <div id="camera-section">
      <video id="camera-preview" autoplay muted playsinline></video>
      <div class="cam-badge">&#x1F7E2; LIVE</div>
    </div>
    <canvas id="capture-canvas" style="display:none;"></canvas>

    <!-- Pipeline steps -->
    <div class="steps">
      <span class="step" id="step-mic">&#x1F3A4; Voice</span>
      <span class="step" id="step-bedrock">&#x1F916; Bedrock</span>
      <span class="step" id="step-bunq">&#x1F3E6; bunq</span>
      <span class="step" id="step-risk">&#x1F6E1;&#xFE0F; Risk</span>
    </div>

    <!-- Mic button — Web Speech API -->
    <button class="mic-btn" id="mic-btn" onclick="toggleListening()">
      <span id="mic-label">Tap to speak</span>
    </button>
    <div id="mic-status"></div>

    <!-- Text input fallback -->
    <div class="input-row">
      <input
        class="finn-input" id="finn-input" type="text"
        placeholder="Or type: what&#x27;s my balance? Send &#x20AC;10 to Sara&#x2026;"
        onkeydown="if(event.key==='Enter') askFinnText()"
      >
      <button class="send-btn" onclick="askFinnText()">&#x279C;</button>
    </div>

    <div class="spinner" id="spinner">Processing&#x2026;</div>

    <div class="finn-response" id="finn-response">
      <div class="finn-name">FINN</div>
      <div id="finn-text"></div>
    </div>

    <!-- Risk Analysis Debug Panel (demo mode only) -->
    <div id="risk-panel">
      <div class="risk-header">&#x26A0;&#xFE0F; FRAUD ANALYSIS</div>
      <div class="risk-bar-wrap"><div id="risk-bar"></div></div>
      <div class="risk-meta">
        <span id="risk-rec">--</span>
        <span id="risk-score-text">0%</span>
      </div>
      <div id="risk-reason"></div>
      <button class="risk-toggle-btn" onclick="toggleRiskDetails()">Show signals &#x25BE;</button>
      <div id="risk-details-body"></div>
    </div>
  </div>
</div>

<!-- Floating fraud analysis panel — visible at all times, top-right -->
<div id="risk-float">
  <div class="rf-header">&#x26A0;&#xFE0F; FRAUD ANALYSIS</div>
  <div class="rf-bar-wrap"><div id="risk-float-bar"></div></div>
  <div class="rf-meta">
    <span id="risk-float-rec">--</span>
    <span id="risk-float-score">0%</span>
  </div>
  <div id="risk-float-reason"></div>
  <button class="rf-toggle" onclick="document.getElementById('risk-float-signals').style.display=document.getElementById('risk-float-signals').style.display==='block'?'none':'block'">Signals &#x25BE;</button>
  <div id="risk-float-signals"></div>
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
let cameraStream = null;
let cameraPopup  = null;
const SESSION_ID_KEY = 'finnSessionId';
let SESSION_ID = localStorage.getItem(SESSION_ID_KEY);
if (!SESSION_ID) {{
  SESSION_ID = (crypto.randomUUID ? crypto.randomUUID() : 'finn-' + Math.random().toString(36).slice(2));
  localStorage.setItem(SESSION_ID_KEY, SESSION_ID);
}}
console.log('Finn BACKEND endpoint:', BACKEND, 'session:', SESSION_ID);

// ── Pipeline step indicator helpers ──────────────────────────────────────────
const STEPS = ['step-mic','step-bedrock','step-bunq','step-risk'];
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

// ── Camera helpers ────────────────────────────────────────────────────────────
async function initCamera() {{
  const video = document.getElementById('camera-preview');
  if (!video) return;
  if (cameraStream) {{ openCameraWindow(); return; }}
  try {{
    cameraStream = await navigator.mediaDevices.getUserMedia({{
      video: {{ width: 320, height: 240, facingMode: 'user' }}, audio: false
    }});
    video.srcObject = cameraStream;
    await video.play();
    document.getElementById('camera-section').style.display = 'block';
    openCameraWindow();
  }} catch (e) {{
    console.warn('Camera unavailable:', e);
  }}
}}

function openCameraWindow() {{
  if (cameraPopup && !cameraPopup.closed) return;
  cameraPopup = window.open('', 'FinnCamera', 'width=840,height=420,top=60,left=60,resizable=yes');
  if (!cameraPopup) {{ return; }}

  // Build HTML using an array of double-quoted strings — no \' issues
  var parts = [
    "<!DOCTYPE html><html><head><title>Finn Identity Verification</title>",
    "<style>*{{margin:0;padding:0;box-sizing:border-box}}body{{background:#0a0a0a;font-family:sans-serif;display:flex;flex-direction:column;height:100vh}}.panels{{display:flex;flex:1;gap:2px;background:#1a1a1a}}.panel{{flex:1;display:flex;flex-direction:column;overflow:hidden}}.lbl{{font-size:11px;font-weight:700;letter-spacing:1px;padding:6px 10px;text-align:center}}.ll{{background:#052e16;color:#22c55e}}.rl{{background:#1e1b4b;color:#a78bfa}}video{{width:100%;flex:1;object-fit:cover;display:block}}img.ri{{width:100%;flex:1;object-fit:cover;display:block}}.ph{{flex:1;display:flex;align-items:center;justify-content:center;color:#555;font-size:13px}}.st{{font-size:11px;padding:5px 10px;background:#111;color:#555;text-align:center;border-top:1px solid #222}}</style>",
    "</head><body>",
    "<div class=panels><div class=panel><div class='lbl ll'>LIVE CAMERA</div><video id=v autoplay muted playsinline></video></div>",
    "<div class=panel><div class='lbl rl'>ENROLLED REFERENCE</div><div id=rw class=ph>Loading...</div></div></div>",
    "<div class=st id=st>Captured once per transaction</div>",
    "</body></html>"
  ];
  cameraPopup.document.open();
  cameraPopup.document.write(parts.join(""));
  cameraPopup.document.close();

  // Wire the existing camera stream — no second getUserMedia needed
  var vid = cameraPopup.document.getElementById("v");
  if (vid && cameraStream) vid.srcObject = cameraStream;

  // Fetch enrolled reference image and inject via DOM (no innerHTML string issues)
  fetch(BACKEND + "/debug/enrolled/eva")
    .then(function(r) {{ return r.json(); }})
    .then(function(d) {{
      if (!cameraPopup || cameraPopup.closed) return;
      var wrap = cameraPopup.document.getElementById("rw");
      var st   = cameraPopup.document.getElementById("st");
      if (d.image_b64) {{
        var img = cameraPopup.document.createElement("img");
        img.className = "ri";
        img.src = "data:image/jpeg;base64," + d.image_b64;
        wrap.textContent = "";
        wrap.appendChild(img);
        if (st) st.textContent = "Reference: " + (d.method || "local") + (d.face_id ? " | face_id: " + d.face_id : " | Claude Vision");
      }} else {{
        wrap.textContent = "No reference image stored";
      }}
    }})
    .catch(function(e) {{ console.warn("Could not load enrolled image:", e); }});
}}

function stopCamera() {{
  if (cameraStream) {{
    cameraStream.getTracks().forEach(t => t.stop());
    cameraStream = null;
  }}
  if (cameraPopup && !cameraPopup.closed) cameraPopup.close();
  cameraPopup = null;
  const cs = document.getElementById('camera-section');
  if (cs) cs.style.display = 'none';
}}

async function captureFrame() {{
  const video  = document.getElementById('camera-preview');
  const canvas = document.getElementById('capture-canvas');
  if (!video || !canvas || !cameraStream || video.readyState < 2 || video.videoWidth === 0) return null;
  canvas.width  = video.videoWidth  || 320;
  canvas.height = video.videoHeight || 240;
  canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height);
  return new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', 0.85));
}}

function isPaymentIntent(text) {{
  return /(send|pay|transfer|payment|request|invoice|charge|link)/i.test(text);
}}

// ── Risk panel helpers ────────────────────────────────────────────────────────
function updateRiskPanel(risk) {{
  const panel = document.getElementById('risk-panel');
  if (!panel || !risk) return;

  const score = risk.risk_score || 0;
  const rec   = risk.recommendation || 'ALLOW';
  const REC_COLORS = {{
    ALLOW: '#22c55e', CHALLENGE: '#eab308',
    HOLD:  '#f97316', REVIEW:    '#ef4444', BLOCK: '#dc2626'
  }};
  const color = REC_COLORS[rec] || '#666';

  const bar = document.getElementById('risk-bar');
  if (bar) {{ bar.style.width = (score * 100).toFixed(0) + '%'; bar.style.background = color; }}

  const recEl = document.getElementById('risk-rec');
  if (recEl) {{ recEl.textContent = rec; recEl.style.color = color; }}

  const scoreEl = document.getElementById('risk-score-text');
  if (scoreEl) scoreEl.textContent = (score * 100).toFixed(0) + '% risk';

  const reasonEl = document.getElementById('risk-reason');
  if (reasonEl) reasonEl.textContent = risk.reason || '';

  const body = document.getElementById('risk-details-body');
  if (body && risk.signals) {{
    const active = Object.entries(risk.signals)
      .filter(([, v]) => v)
      .map(([k]) => '• ' + k.replace(/_/g, ' '));
    body.textContent = active.length ? active.join('\\n') : '(no active signals)';
    if (risk.details && risk.details.face_match) {{
      const fm = risk.details.face_match;
      body.textContent += '\\n\\nFace match: ' + (fm.matched ? '✓ ' + fm.similarity + '%' : '✗ no match');
    }}
  }}

  panel.style.display = 'block';

  // ── Also drive the always-visible floating panel ──
  const fp = document.getElementById('risk-float');
  if (fp) {{
    const fb = document.getElementById('risk-float-bar');
    if (fb) {{ fb.style.width = (score * 100).toFixed(0) + '%'; fb.style.background = color; }}
    const fr = document.getElementById('risk-float-rec');
    if (fr) {{ fr.textContent = rec; fr.style.color = color; }}
    const fs = document.getElementById('risk-float-score');
    if (fs) fs.textContent = (score * 100).toFixed(0) + '% risk';
    const freason = document.getElementById('risk-float-reason');
    if (freason) freason.textContent = risk.reason || '';
    const fsig = document.getElementById('risk-float-signals');
    if (fsig && risk.signals) {{
      const active = Object.entries(risk.signals).filter(([,v])=>v).map(([k])=>'• '+k.replace(/_/g,' '));
      fsig.textContent = active.length ? active.join('\\n') : '(no active signals)';
    }}
    fp.style.display = 'block';
  }}
}}

function toggleRiskDetails() {{
  const body = document.getElementById('risk-details-body');
  const btn  = document.querySelector('.risk-toggle-btn');
  if (!body) return;
  const open = body.style.display === 'block';
  body.style.display = open ? 'none' : 'block';
  if (btn) btn.textContent = open ? 'Show signals ▾' : 'Hide signals ▴';
}}

// ── Backend health check ──────────────────────────────────────────────────────
async function checkBackend() {{
  const el = document.getElementById('backend-status');
  if (!el) return;
  try {{
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 4000);
    const r = await fetch(BACKEND + '/health', {{ signal: ctrl.signal }});
    clearTimeout(timer);
    const d = await r.json();
    el.textContent = '✓ Backend connected · ' + (d.bedrock_model || '');
    el.style.color = '#22c55e';
  }} catch (e) {{
    el.textContent = '✗ Backend offline — refresh the page';
    el.style.color = '#f87171';
  }}
}}

// ── Modal open/close ──────────────────────────────────────────────────────────
function openVoice() {{
  document.getElementById('voice-modal').classList.add('open');
  resetSteps();
  setTimeout(() => document.getElementById('finn-input').focus(), 100);
  checkBackend();
  // Request camera permission immediately on open (works on Chrome/localhost)
  initCamera();
  // Pre-request mic permission so the browser prompt appears on startup
  if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {{
    navigator.mediaDevices.getUserMedia({{ audio: true }})
      .then(s => s.getTracks().forEach(t => t.stop()))
      .catch(e => console.warn('Mic permission denied:', e));
  }}
}}
function closeVoice() {{
  stopListening();
  stopCamera();
  document.getElementById('voice-modal').classList.remove('open');
}}

// ── Show response + TTS ───────────────────────────────────────────────────────
function showResponse(text) {{
  document.getElementById('spinner').classList.remove('show');
  let display = text;
  if (typeof text === 'object' && text !== null) {{
    if (text.message) {{
      display = text.message;
    }} else if (text.error) {{
      const tool = text.tool ? ' (' + text.tool.replace(/_/g, ' ') + ')' : '';
      const detail = text.details ? ': ' + text.details : '';
      display = text.error + tool + detail;
    }} else {{
      display = JSON.stringify(text, null, 2);
    }}
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
// Auto-open modal but do NOT auto-start mic or camera (both need user gesture)
window.addEventListener('load', () => {{ setTimeout(() => openVoice(), 600); }});

// ── Text query → /query endpoint ─────────────────────────────────────────────
async function askFinnText() {{
  const input = document.getElementById('finn-input');
  const text = input.value.trim();
  if (!text) return;
  input.value = '';
  if (!cameraStream) initCamera();  // user gesture — request camera permission
  await sendTextToBackend(text);
}}

// ── Browser speech recognition → /query endpoint ────────────────────────────
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
let recognition = null;
let isListening = false;
let stopRequested = false;
let accumulatedTranscript = '';

function toggleListening() {{
  if (!cameraStream) initCamera();   // first mic click = user gesture → request camera
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
    document.getElementById('mic-btn').classList.add('recording');
    document.getElementById('mic-label').textContent = 'Listening...';
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
        if (lower.includes('i am done') || lower.includes("i'm done") || lower.includes('im done') || lower.includes('i am finished') || lower.includes('i m done')) {{
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
      document.getElementById('mic-btn').classList.remove('recording');
      document.getElementById('mic-label').textContent = 'Tap to speak';
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
    document.getElementById('mic-btn').classList.remove('recording');
    document.getElementById('mic-label').textContent = 'Tap to speak';
  }}
}}

async function sendTextToBackend(text) {{
  resetSteps();
  document.getElementById('finn-response').classList.remove('show');
  document.getElementById('risk-panel') && (document.getElementById('risk-panel').style.display = 'none');
  document.getElementById('spinner').classList.add('show');
  document.getElementById('mic-status').textContent = '';

  let endpoint, fetchOptions;

  if (isPaymentIntent(text)) {{
    // All payment intents must go through /query-with-frame so fraud check is enforced
    setStep('step-risk', 'active');
    const frameBlob = cameraStream ? await captureFrame() : null;
    const formData = new FormData();
    formData.append('text', text);
    formData.append('session_id', SESSION_ID);
    if (frameBlob) formData.append('frame', frameBlob, 'frame.jpg');
    endpoint    = BACKEND + '/query-with-frame';
    fetchOptions = {{ method: 'POST', body: formData }};
  }} else {{
    endpoint    = BACKEND + '/query';
    fetchOptions = {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{ text, session_id: SESSION_ID }}),
    }};
  }}

  setStep('step-bedrock', 'active');

  try {{
    console.log('Fetch', endpoint);
    const res  = await fetch(endpoint, fetchOptions);
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Backend error');

    // Risk step feedback
    if (data.risk) {{
      const rec = data.risk.recommendation || 'ALLOW';
      const stepState = rec === 'ALLOW' ? 'done' : rec === 'BLOCK' ? 'error' : 'active';
      setStep('step-risk', stepState);
      updateRiskPanel(data.risk);
    }} else {{
      setStep('step-risk', 'done');
    }}

    setStep('step-bedrock', 'done');

    if (data.status === 'blocked' || data.status === 'held') {{
      document.getElementById('spinner').classList.remove('show');
      document.getElementById('finn-text').textContent = data.response;
      document.getElementById('finn-response').classList.add('show');
      setStep('step-bedrock', 'done');
      setStep('step-bunq', data.status === 'blocked' ? 'error' : 'active');
      speak(data.response);
      return;
    }}

    setStep('step-bunq', 'active');
    document.getElementById('mic-status').textContent = 'Executing bunq action…';
    await new Promise(r => setTimeout(r, 400));
    showResponse(data.response);
  }} catch (e) {{
    showError(e.message + ' — ' + endpoint);
  }}
}}
</script>

</body>
</html>"""

components.html(HTML, height=920, scrolling=False)
