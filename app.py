import streamlit as st
import streamlit.components.v1 as components
import os

st.set_page_config(
    page_title="bunq",
    page_icon="💜",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# Minimal Streamlit chrome removal
st.markdown("""
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
""", unsafe_allow_html=True)

api_key = os.environ.get("ANTHROPIC_API_KEY", "")

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
  position: relative;
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
.status-right {{ display: flex; gap: 8px; align-items: center; }}

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

/* ── Search / Finn ── */
.search-bar {{
  margin: 0 16px 18px;
  background: #1a1a1a;
  border-radius: 14px;
  padding: 13px 16px;
  display: flex;
  align-items: center;
  gap: 10px;
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

/* base card */
.card {{
  border-radius: 20px;
  padding: 16px;
  min-height: 108px;
  position: relative;
  overflow: hidden;
}}

/* Total balance – purple */
.card-balance {{
  background: linear-gradient(145deg, #6d28d9 0%, #8b5cf6 55%, #c084fc 100%);
}}
.card-balance .lbl {{
  font-size: 11px;
  font-weight: 500;
  opacity: .85;
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  gap: 5px;
}}
.card-balance .amt {{
  font-size: 23px;
  font-weight: 800;
  line-height: 1.1;
}}
.card-balance .sub {{
  font-size: 13px;
  font-weight: 500;
  opacity: .75;
  margin-top: 2px;
}}

/* Summer Vacay */
.card-vacay {{
  background: #181818;
  border: 1px solid #252525;
}}
.card-vacay .ttl {{
  font-size: 13px;
  font-weight: 700;
  margin-bottom: 14px;
}}
.card-vacay .icons {{
  display: flex;
  gap: 8px;
  font-size: 20px;
}}

/* Main – orange dot */
.card-main {{
  background: #181818;
  border: 1px solid #252525;
}}
.card-savings {{
  background: #181818;
  border: 1px solid #252525;
}}
.dot {{
  width: 9px; height: 9px;
  border-radius: 50%;
  display: inline-block;
  margin-right: 6px;
  flex-shrink: 0;
}}
.dot-orange {{ background: #f97316; }}
.dot-green  {{ background: #22c55e; }}
.card-ttl {{
  font-size: 13px;
  font-weight: 700;
  margin-bottom: 8px;
  display: flex;
  align-items: center;
}}
.card-amt {{
  font-size: 20px;
  font-weight: 800;
}}

/* Everyday – full width */
.card-everyday {{
  grid-column: span 2;
  background: linear-gradient(135deg, #1a1a2e 0%, #2d1b69 55%, #1a1a2e 100%);
  border: 1px solid #3a2a6a;
  min-height: 72px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 20px;
}}
.everyday-left .lbl {{
  font-size: 11px;
  font-weight: 600;
  color: #999;
  margin-bottom: 4px;
}}
.everyday-left .num {{
  font-size: 15px;
  font-weight: 700;
  letter-spacing: 2px;
}}
.mc {{ display: flex; align-items: center; }}
.mc-c {{
  width: 28px; height: 28px;
  border-radius: 50%;
}}
.mc-r {{ background: #eb001b; margin-right: -10px; z-index: 1; }}
.mc-o {{ background: #f79e1b; opacity: .9; }}

/* ── Quick actions ── */
.quick-actions {{
  display: flex;
  justify-content: center;
  gap: 48px;
  padding: 22px 16px 10px;
}}
.qbtn {{
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  background: none;
  border: none;
  color: #fff;
}}
.qbtn-icon {{
  width: 52px; height: 52px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  font-weight: 700;
}}
.qbtn-label {{ color: #777; font-size: 12px; font-weight: 500; }}
.ic-pay {{ background: linear-gradient(135deg,#f97316,#fb923c); }}
.ic-req {{ background: linear-gradient(135deg,#3b82f6,#60a5fa); }}
.ic-add {{ background: linear-gradient(135deg,#7c3aed,#a78bfa); }}

/* ── Bottom nav ── */
.bottom-nav {{
  position: fixed;
  bottom: 0;
  left: 50%;
  transform: translateX(-50%);
  width: 100%;
  max-width: 390px;
  background: #101010;
  border-top: 1px solid #1e1e1e;
  display: flex;
  justify-content: space-around;
  padding: 10px 0 22px;
  z-index: 100;
}}
.nav-item {{
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 3px;
  cursor: pointer;
  color: #444;
  font-size: 10px;
  font-weight: 500;
}}
.nav-item.active {{ color: #fff; }}
.nav-icon {{ font-size: 20px; }}
.nav-dot {{
  width: 4px; height: 4px;
  border-radius: 50%;
  background: #7c3aed;
  margin: 0 auto;
}}

/* ── Voice FAB ── */
#voice-fab {{
  position: fixed;
  bottom: 90px;
  right: max(12px, calc(50% - 195px + 12px));
  width: 52px; height: 52px;
  border-radius: 50%;
  background: linear-gradient(135deg, #7c3aed, #a78bfa);
  border: none;
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  font-size: 22px;
  box-shadow: 0 4px 20px rgba(124,58,237,.55);
  z-index: 200;
  transition: transform .15s, box-shadow .15s;
}}
#voice-fab:hover {{
  transform: scale(1.08);
  box-shadow: 0 6px 28px rgba(124,58,237,.75);
}}
#voice-fab.listening {{
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
  position: fixed;
  inset: 0;
  z-index: 300;
  align-items: flex-end;
  justify-content: center;
  padding-bottom: 110px;
}}
#voice-modal.open {{ display: flex; }}
.modal-backdrop {{
  position: absolute;
  inset: 0;
  background: rgba(0,0,0,.55);
}}
.modal-sheet {{
  position: relative;
  width: calc(100% - 32px);
  max-width: 358px;
  background: #161616;
  border: 1px solid #2a2a2a;
  border-radius: 24px;
  padding: 20px;
  z-index: 1;
  box-shadow: 0 16px 60px rgba(0,0,0,.7);
}}
.modal-tag {{
  font-size: 10px;
  font-weight: 700;
  color: #a78bfa;
  letter-spacing: 1px;
  margin-bottom: 6px;
}}
.modal-title {{
  font-size: 17px;
  font-weight: 700;
  margin-bottom: 4px;
}}
.modal-sub {{
  font-size: 12px;
  color: #666;
  margin-bottom: 16px;
}}
.modal-close {{
  position: absolute;
  top: 14px; right: 16px;
  background: #252525;
  border: none;
  color: #aaa;
  width: 28px; height: 28px;
  border-radius: 50%;
  cursor: pointer;
  font-size: 14px;
  display: flex; align-items: center; justify-content: center;
}}
.modal-close:hover {{ color: #fff; background: #333; }}

/* input row */
.input-row {{
  display: flex;
  gap: 8px;
  margin-bottom: 10px;
}}
.finn-input {{
  flex: 1;
  background: #1e1e1e;
  border: 1px solid #333;
  border-radius: 12px;
  padding: 10px 14px;
  color: #fff;
  font-size: 13px;
  outline: none;
}}
.finn-input::placeholder {{ color: #555; }}
.finn-input:focus {{ border-color: #7c3aed; }}
.send-btn {{
  background: linear-gradient(135deg,#7c3aed,#a78bfa);
  border: none;
  border-radius: 12px;
  padding: 10px 14px;
  color: #fff;
  font-size: 16px;
  cursor: pointer;
}}

/* mic button */
.mic-btn {{
  width: 100%;
  background: #1e1e1e;
  border: 1px solid #2a2a2a;
  border-radius: 12px;
  color: #aaa;
  padding: 10px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin-bottom: 10px;
}}
.mic-btn:hover {{ background: #222; }}
.mic-btn.active {{
  background: #1a0a0a;
  border-color: #dc2626;
  color: #f87171;
}}

/* response bubble */
.finn-response {{
  background: #0d0d1a;
  border: 1px solid #3a2a6a44;
  border-radius: 14px;
  padding: 12px 14px;
  font-size: 13px;
  color: #ddd;
  line-height: 1.6;
  display: none;
}}
.finn-response.show {{ display: block; }}
.finn-response .finn-name {{
  color: #a78bfa;
  font-weight: 700;
  margin-bottom: 4px;
  font-size: 11px;
  letter-spacing: .5px;
}}

/* mic status */
#mic-status {{
  font-size: 11px;
  color: #555;
  text-align: center;
  margin-top: 6px;
  min-height: 16px;
}}

/* spinner */
.spinner {{
  display: none;
  text-align: center;
  color: #666;
  font-size: 12px;
  padding: 8px 0;
}}
.spinner.show {{ display: block; }}
</style>
</head>
<body>

<div class="phone">

  <!-- Status bar -->
  <div class="status-bar">
    <span>10:10</span>
    <div class="status-right">
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

  <!-- Ask Finn search bar -->
  <div class="search-bar">
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

    <!-- Total balance -->
    <div class="card card-balance">
      <div class="lbl"><span>&#x2736;</span> Total balance</div>
      <div class="amt">&euro; 2,433</div>
      <div class="sub">.00</div>
    </div>

    <!-- Summer Vacay -->
    <div class="card card-vacay">
      <div class="ttl">Summer Vacay</div>
      <div class="icons">&#x2708;&#xFE0F; &#x1F3CA; &#x1F381;</div>
    </div>

    <!-- Main -->
    <div class="card card-main">
      <div class="card-ttl">
        <span class="dot dot-orange"></span>Main
      </div>
      <div class="card-amt">&euro; 900.00</div>
    </div>

    <!-- Savings -->
    <div class="card card-savings">
      <div class="card-ttl">
        <span class="dot dot-green"></span>Savings
      </div>
      <div class="card-amt">&euro; 310.00</div>
    </div>

    <!-- Everyday card -->
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

  <!-- Quick actions: Pay / Request / Add -->
  <div class="quick-actions">
    <button class="qbtn">
      <div class="qbtn-icon ic-pay">&#x2191;</div>
      <span class="qbtn-label">Pay</span>
    </button>
    <button class="qbtn">
      <div class="qbtn-icon ic-req">&#x2193;</div>
      <span class="qbtn-label">Request</span>
    </button>
    <button class="qbtn">
      <div class="qbtn-icon ic-add">&#xFF0B;</div>
      <span class="qbtn-label">Add</span>
    </button>
  </div>

</div>

<!-- Bottom nav -->
<div class="bottom-nav">
  <div class="nav-item active">
    <div class="nav-icon">&#x1F3E0;</div>
    <span>Home</span>
    <div class="nav-dot"></div>
  </div>
  <div class="nav-item">
    <div class="nav-icon">&#x2708;&#xFE0F;</div>
    <span>Travel</span>
  </div>
  <div class="nav-item">
    <div class="nav-icon">&#x1F4CA;</div>
    <span>Budgeting</span>
  </div>
  <div class="nav-item">
    <div class="nav-icon">&#x1F4C8;</div>
    <span>Stocks</span>
  </div>
  <div class="nav-item">
    <div class="nav-icon">&#x20BF;</div>
    <span>Crypto</span>
  </div>
</div>

<!-- Voice FAB -->
<button id="voice-fab" title="Talk to Finn" onclick="openVoice()">&#x1F3A4;</button>

<!-- Voice modal -->
<div id="voice-modal">
  <div class="modal-backdrop" onclick="closeVoice()"></div>
  <div class="modal-sheet">
    <button class="modal-close" onclick="closeVoice()">&#x2715;</button>
    <div class="modal-tag">&#x2736; FINN VOICE</div>
    <div class="modal-title">Ask Finn</div>
    <div class="modal-sub">Speak or type — Finn answers out loud.</div>

    <button class="mic-btn" id="mic-btn" onclick="toggleMic()">
      <span id="mic-icon">&#x1F3A4;</span>
      <span id="mic-label">Tap to speak</span>
    </button>
    <div id="mic-status"></div>

    <div class="input-row" style="margin-top:10px;">
      <input
        class="finn-input"
        id="finn-input"
        type="text"
        placeholder="What&#x27;s my balance? Send &#x20AC;10 to Sara&#x2026;"
        onkeydown="if(event.key==='Enter') askFinn()"
      >
      <button class="send-btn" onclick="askFinn()">&#x279C;</button>
    </div>

    <div class="spinner" id="spinner">Finn is thinking&#x2026;</div>

    <div class="finn-response" id="finn-response">
      <div class="finn-name">FINN</div>
      <div id="finn-text"></div>
    </div>
  </div>
</div>

<script>
const API_KEY = "{api_key}";

// ── Modal open/close ──────────────────────────────────────────────────
function openVoice() {{
  document.getElementById('voice-modal').classList.add('open');
  document.getElementById('finn-input').focus();
}}
function closeVoice() {{
  document.getElementById('voice-modal').classList.remove('open');
  stopMic();
}}

// ── Ask Finn (Claude API) ──────────────────────────────────────────────
async function askFinn() {{
  const input = document.getElementById('finn-input');
  const text  = input.value.trim();
  if (!text) return;

  const spinner  = document.getElementById('spinner');
  const response = document.getElementById('finn-response');
  const finnText = document.getElementById('finn-text');

  spinner.classList.add('show');
  response.classList.remove('show');

  try {{
    const res = await fetch('https://api.anthropic.com/v1/messages', {{
      method: 'POST',
      headers: {{
        'Content-Type': 'application/json',
        'x-api-key': API_KEY,
        'anthropic-version': '2023-06-01',
        'anthropic-dangerous-direct-browser-access': 'true'
      }},
      body: JSON.stringify({{
        model: 'claude-haiku-4-5-20251001',
        max_tokens: 200,
        system: 'You are Finn, bunq\\'s friendly AI banking assistant. ' +
                'Answer in 1-2 sentences, warm and concise — this is a voice interface. ' +
                'User is Eva. Balances: Total €2,433 | Main €900 | Savings €310.',
        messages: [{{ role: 'user', content: text }}]
      }})
    }});

    if (!res.ok) {{
      const err = await res.json();
      throw new Error(err.error?.message || 'API error ' + res.status);
    }}

    const data = await res.json();
    const reply = data.content[0].text;

    spinner.classList.remove('show');
    finnText.textContent = reply;
    response.classList.add('show');
    input.value = '';

    speak(reply);
  }} catch(e) {{
    spinner.classList.remove('show');
    finnText.textContent = 'Sorry, I ran into an issue: ' + e.message;
    response.classList.add('show');
  }}
}}

// ── TTS ───────────────────────────────────────────────────────────────
function speak(text) {{
  if (!window.speechSynthesis) return;
  window.speechSynthesis.cancel();
  const utt = new SpeechSynthesisUtterance(text);
  utt.rate  = 1.0;
  utt.pitch = 1.05;
  const voices = window.speechSynthesis.getVoices();
  const v = voices.find(v =>
    v.name.includes('Samantha') ||
    v.name.toLowerCase().includes('female') ||
    (v.lang === 'en-US' && v.name.includes('Google'))
  );
  if (v) utt.voice = v;
  window.speechSynthesis.speak(utt);
}}

// ── Speech recognition ────────────────────────────────────────────────
let recog = null;
let isListening = false;

function toggleMic() {{
  isListening ? stopMic() : startMic();
}}

function startMic() {{
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) {{
    document.getElementById('mic-status').textContent = 'Speech recognition not supported.';
    return;
  }}
  recog = new SR();
  recog.lang = 'en-US';
  recog.interimResults = false;
  recog.maxAlternatives = 1;

  recog.onstart = () => {{
    isListening = true;
    document.getElementById('voice-fab').classList.add('listening');
    document.getElementById('mic-btn').classList.add('active');
    document.getElementById('mic-label').textContent = 'Listening…';
    document.getElementById('mic-icon').textContent = '⏹';
    document.getElementById('mic-status').textContent = '🔴 Speak now…';
  }};

  recog.onresult = (e) => {{
    const transcript = e.results[0][0].transcript;
    document.getElementById('finn-input').value = transcript;
    document.getElementById('mic-status').textContent = '✓ Heard: ' + transcript;
    stopMic();
    askFinn();
  }};

  recog.onerror = (e) => {{
    document.getElementById('mic-status').textContent = 'Error: ' + e.error;
    stopMic();
  }};

  recog.onend = () => stopMic();

  recog.start();
}}

function stopMic() {{
  if (recog) {{ try {{ recog.stop(); }} catch(e) {{}} recog = null; }}
  isListening = false;
  document.getElementById('voice-fab').classList.remove('listening');
  document.getElementById('mic-btn').classList.remove('active');
  document.getElementById('mic-label').textContent = 'Tap to speak';
  document.getElementById('mic-icon').textContent = '🎤';
}}

// Preload voices
window.speechSynthesis && window.speechSynthesis.getVoices();
</script>

</body>
</html>"""

components.html(HTML, height=820, scrolling=False)
