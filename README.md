# ⚒️ FORGE

**Framework for Orchestrated Reasoning & Generation of Engines**

> The world's first autonomous AI security framework.  
> AI pentesting AI. Self-replicating swarms. 24/7 watchdog. Works on any LLM.

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![OWASP LLM Top 10](https://img.shields.io/badge/OWASP-LLM%20Top%2010-red.svg)](https://owasp.org/www-project-top-10-for-large-language-model-applications/)
[![Ethical Use Only](https://img.shields.io/badge/use-ethical%20only-green.svg)](#ethics)

---

## What is FORGE?

FORGE is a **living security system** — not just a tool.

```
Traditional tools:  static, human-operated, single purpose
FORGE:              self-replicating, AI-powered, self-improving

It builds its own tools mid-run.
It copies itself into parallel workers.
It learns from every session forever.
It audits AI systems using AI.
It watches your AI 24/7 and alerts when attacked.
```

---

## Quick Start

```bash
git clone https://github.com/umangkartikey/forge
cd forge
pip install -r requirements.txt
export ANTHROPIC_API_KEY=your_key_here
python forge.py
```

Or use any open source model — free, no API key needed:
```bash
# Install Ollama: curl https://ollama.ai/install.sh | sh
ollama pull llama3.1
FORGE_BACKEND=ollama python forge.py
```

---

## All Tools — Complete CLI Reference

---

### forge.py — AI Tool Builder

The core. Give it a goal, it builds a Python security tool using AI + genetic evolution.

```bash
python forge.py

FORGE > build a port scanner with banner grabbing
FORGE > build a subdomain enumerator
FORGE > build a JWT token analyzer

# Evolution
FORGE > genetic          # natural selection — keep best, mutate rest
FORGE > ai2ai            # 5 AI agents debate and refine the tool
FORGE > improve          # improve last built tool

# Autonomous mode
FORGE > autopilot        # AI picks what to build and does it
FORGE > adapt recon this IP: 192.168.1.1

# Tool management
FORGE > list             # all built tools
FORGE > test             # run tests on current tool
FORGE > save mytool      # save to modules/
FORGE > load mytool      # load saved tool
```

---

### forge_meta.py — Metasploit-Style Console

Full framework with modules, natural language mode, autopilot, and surface mapper.

```bash
python forge_meta.py

# Module workflow
forge-meta > list                       # all modules
forge-meta > use scanner/portscan       # load module
forge-meta > show options               # see options
forge-meta > set TARGET 192.168.1.1     # set target
forge-meta > run                        # execute
forge-meta > back                       # exit module

# Natural language mode
forge-meta > nl scan 192.168.1.1 for open ports
forge-meta > nl find all web services on 10.0.0.0/24
forge-meta > nl check if SSH is vulnerable on 192.168.1.1

# Surface mapping
forge-meta > map 192.168.1.1            # full attack surface

# Autopilot
forge-meta > autopilot 192.168.1.1      # AI does everything

# Built-in modules
forge-meta > use scanner/portscan       # TCP port scanner
forge-meta > use recon/http             # HTTP headers, tech stack
forge-meta > use recon/osint            # DNS, WHOIS, subdomains
forge-meta > use brute/ssh              # SSH brute force
forge-meta > use cracker/hash           # hash cracker
forge-meta > use util/passgen           # password generator
```

---

### forge_swarm.py — Self-Replicating Hive Mind

FORGE copies itself into N parallel workers. All share a live hive mind.

```bash
python forge_swarm.py

forge-swarm > swarm 192.168.1.0/24                     # swarm a network
forge-swarm > swarm http://target.com                  # swarm web target
forge-swarm > swarm 192.168.1.1 --workers 8            # custom worker count
forge-swarm > swarm 192.168.1.1 --goal "full recon"    # with goal

# Monitor
forge-swarm > status        # live worker status
forge-swarm > findings      # all findings
forge-swarm > modules       # modules built by swarm
forge-swarm > hive          # raw hive mind state

# Control
forge-swarm > kill          # stop all workers
forge-swarm > clean         # wipe hive state

# CLI
python forge_swarm.py --target 192.168.1.1
python forge_swarm.py --target 192.168.1.1 --workers 10 --goal "full recon"
```

---

### forge_core_ai.py — Universal Model Backend

Switch FORGE to ANY AI model with one environment variable.

```bash
python forge_core_ai.py check       # test connection
python forge_core_ai.py backends    # list all backends
python forge_core_ai.py models      # list Ollama models
python forge_core_ai.py pull llama3.1        # pull Ollama model
python forge_core_ai.py setup ollama         # setup guide
python forge_core_ai.py setup groq           # setup guide
```

Switch backends:
```bash
# Claude (default)
python forge.py

# Llama locally — free, private
FORGE_BACKEND=ollama FORGE_MODEL=llama3.1 python forge.py

# DeepSeek — best for code
FORGE_BACKEND=ollama FORGE_MODEL=deepseek-coder-v2 python forge.py

# Groq — ultra fast, free tier
FORGE_BACKEND=groq GROQ_API_KEY=your_key python forge.py

# Together.ai — 100+ models
FORGE_BACKEND=together TOGETHER_API_KEY=your_key \
  FORGE_MODEL=meta-llama/Llama-3-70b-chat-hf python forge.py

# LM Studio / Jan / any local server
FORGE_BACKEND=custom FORGE_BASE_URL=http://localhost:1234/v1 python forge.py

# GPT-4o
FORGE_BACKEND=openai OPENAI_API_KEY=your_key FORGE_MODEL=gpt-4o python forge.py
```

Environment variables:
```bash
FORGE_BACKEND       # anthropic|ollama|groq|openai|together|custom
FORGE_MODEL         # model name (auto-selected if blank)
FORGE_BASE_URL      # custom API endpoint
FORGE_API_KEY       # API key override
FORGE_MAX_RETRIES   # retries on failure (default: 3)
FORGE_TIMEOUT       # timeout seconds (default: 60)
FORGE_TEMPERATURE   # temperature (default: 0.7)
```

---

### forge_learn.py — SQLite Learning Brain

FORGE remembers everything. Learns patterns. Evolves its own prompts.

```bash
python forge_learn.py

forge-learn > status      # brain stats
forge-learn > runs        # recent run history with scores
forge-learn > patterns    # learned attack patterns
forge-learn > insights    # distilled knowledge
forge-learn > learn       # import swarm run + full loop
forge-learn > rate        # AI score all findings
forge-learn > extract     # extract patterns
forge-learn > distill     # distill insights
forge-learn > evolve      # genetic algo on prompts
forge-learn > loop        # rate > extract > distill > evolve

# CLI
python forge_learn.py --status
python forge_learn.py --learn
python forge_learn.py --evolve planner
python forge_learn.py --patterns
python forge_learn.py --import findings.json
```

---

### forge_ui.py — Real-Time Web Dashboard

Live web dashboard for swarm status, findings, and brain stats.

```bash
python forge_ui.py               # start on port 7331
python forge_ui.py --port 8080   # custom port

# Open in browser:
# http://localhost:7331
```

Dashboard shows:
- Live swarm workers with progress bars
- Real-time findings stream
- Hive mind message bus
- Module pool (all built modules)
- Brain stats
- Launch controls

---

### forge_llm_pentest.py — AI Pentesting AI

Audit any LLM system against OWASP LLM Top 10. The first tool of its kind.

```bash
python forge_llm_pentest.py

# Load and run a module
llm-pentest > use llm/prompt_injector
llm-pentest > show options
llm-pentest > set TARGET http://your-ai-api.com/v1
llm-pentest > set API_KEY sk-xxx
llm-pentest > set ENDPOINT openai
llm-pentest > run

# All 7 modules
llm-pentest > use llm/prompt_injector        # OWASP LLM01
llm-pentest > use llm/system_prompt_probe    # OWASP LLM06
llm-pentest > use llm/jailbreak_fuzzer       # OWASP LLM01+LLM08
llm-pentest > use llm/rag_leaker             # OWASP LLM06+LLM02
llm-pentest > use llm/agent_hijacker         # OWASP LLM07+LLM08
llm-pentest > use llm/model_fingerprinter    # OWASP LLM10
llm-pentest > use llm/defense_auditor        # OWASP LLM01+LLM04

# Full OWASP LLM Top 10 audit
llm-pentest > audit                          # test local/direct AI
llm-pentest > audit http://your-ai-api.com   # test remote AI

# Useful options per module
llm-pentest > set ENDPOINT direct            # test FORGE's own AI
llm-pentest > set THREADS 10                 # parallel payloads
llm-pentest > set EVOLVE true                # AI generates new attacks
llm-pentest > set MODE classic               # payload subset
```

Options per module:
```
TARGET          API URL (blank = direct mode)
API_KEY         API key
MODEL           Model name
ENDPOINT        direct | openai | anthropic | ollama
THREADS         Parallel threads (default 5)
EVOLVE          AI-generate new variants from what works
MODE            all | classic | roleplay | encoded
TEST_PROMPT     Dangerous prompt for jailbreak testing
```

---

### forge_honeypot.py — AI Attack Trap

Fake vulnerable AI endpoint. Catches and classifies attackers.

```bash
python forge_honeypot.py                    # start on port 8888
python forge_honeypot.py --port 9999        # custom port
python forge_honeypot.py --stats            # view captured attacks
python forge_honeypot.py --export           # export to forge_learn

# Endpoints once running:
# http://localhost:8888/v1/chat/completions  ← attack target
# http://localhost:8888/                     ← live dashboard
# http://localhost:8888/docs                 ← fake API docs
# http://localhost:8888/api/stats            ← JSON stats
```

Test it with FORGE:
```bash
# Terminal 1
python forge_honeypot.py

# Terminal 2 — attack the honeypot
python forge_llm_pentest.py
llm-pentest > use llm/prompt_injector
llm-pentest > set TARGET http://localhost:8888
llm-pentest > set ENDPOINT openai
llm-pentest > run
# Honeypot catches and classifies every probe
```

What it detects and classifies:
```
injection     prompt injection attempts
extraction    system prompt stealing
jailbreak     safety bypass attempts
fingerprint   model identification probes
dos           flood / repetition attacks
agent         indirect prompt injection
rag           RAG data extraction
```

Attacker types:
```
ai_agent      automated tool (Python, curl, HTTP library)
forge         FORGE framework specifically
human         manual testing (browser, natural language)
unknown       unclear
```

---

### forge_overloader.py — LLM Stress Tester

Test your AI's resilience against OWASP LLM04 (Model Denial of Service).

```bash
python forge_overloader.py                  # interactive

# CLI
python forge_overloader.py --target http://localhost:8888 --mode full
python forge_overloader.py --target http://localhost:8888 --mode flood
python forge_overloader.py --target http://localhost:8888 --mode rate

# With options
python forge_overloader.py \
  --target http://your-ai.com/v1 \
  --api-key sk-xxx \
  --model gpt-3.5-turbo \
  --mode full \
  --workers 20 \
  --duration 60

python forge_overloader.py --stats         # past results
```

All modes:
```
full          All phases — recommended
flood         N workers × duration seconds (pure volume)
repetition    "Repeat X 1000 times" — token exhaustion
context       Huge inputs — context window overflow
semantic      Expensive reasoning tasks
recursive     Self-referential / infinite prompts
format        Malformed/adversarial inputs
rate          Rate limit probe only
```

Grades:
```
A  Strong DoS resilience
B  Good, minor improvements needed
C  Moderate risk
D  High risk — rate limiting issues
F  Critical — no protection detected
```

---

### forge_monitor.py — 24/7 AI Watchdog

Runs forever. Pings your AI every N seconds. Alerts on everything unusual.

```bash
# Basic usage
python forge_monitor.py --target http://your-ai.com/v1

# With API key
python forge_monitor.py --target http://your-ai.com/v1 --api-key sk-xxx

# Check every 15 seconds
python forge_monitor.py --target http://localhost:8888 --interval 15

# With Slack alerts
python forge_monitor.py \
  --target http://your-ai.com/v1 \
  --webhook https://hooks.slack.com/services/xxx

# With Discord alerts
python forge_monitor.py \
  --target http://your-ai.com/v1 \
  --webhook https://discord.com/api/webhooks/xxx

# Saved config
python forge_monitor.py --config monitor.json

# Reports
python forge_monitor.py --status           # current status
python forge_monitor.py --incidents        # all past incidents
```

Config file (`monitor.json`):
```json
{
  "target":                 "http://your-ai.com/v1",
  "api_key":                "sk-xxx",
  "model":                  "gpt-3.5-turbo",
  "check_interval":         30,
  "latency_spike_factor":   2.5,
  "latency_warning_ms":     3000,
  "latency_critical_ms":    8000,
  "error_rate_warning":     5.0,
  "error_rate_critical":    15.0,
  "availability_warning":   95.0,
  "attack_burst_threshold": 5,
  "webhook_url":            "https://hooks.slack.com/services/xxx",
  "alert_cooldown":         300,
  "honeypot_db":            "forge_honeypot/attacks.db",
  "learn_export":           true
}
```

Alerts fired when:
```
latency_spike         P95 jumps 2.5x above baseline
latency_warning       P95 exceeds 3000ms
latency_critical      P95 exceeds 8000ms
error_rate_warning    Errors above 5%
error_rate_critical   Errors above 15%
availability_down     Endpoint not responding
attack_burst          5+ attacks in 60 seconds
attack_injection      Prompt injection detected
attack_extraction     System prompt theft attempt
attack_jailbreak      Jailbreak attempt
ai_analysis           AI incident analysis (every 5 min)
```

---

### patch_backends.py — Auto-Patch Script

Wire forge_core_ai.py into all FORGE files in one command.

```bash
python patch_backends.py
```

---

## The Full Defense Stack

```
forge_honeypot.py   →  Lure attackers in
forge_monitor.py    →  Watch 24/7 for threats
forge_llm_pentest   →  Audit on demand
forge_overloader    →  Stress test resilience
forge_learn.py      →  Learn from every attack

The Loop:
  Attacker hits your AI
    → Honeypot catches + classifies them
      → Monitor fires an alert
        → LLM pentest audits the vector
          → Learn loop stores the pattern
            → Next session starts smarter
```

---

## Multi-Model Support

| Backend | Examples | Cost |
|---------|---------|------|
| `anthropic` | claude-sonnet-4-6 | $ |
| `ollama` | llama3.1, deepseek-coder-v2 | Free |
| `groq` | llama-3.1-70b-versatile | Free tier |
| `openai` | gpt-4o | $$ |
| `together` | 100+ open models | $ |
| `custom` | Any OpenAI-compatible endpoint | — |

---

## Ethics

FORGE is built for defenders.

✅ Test systems you own or have written permission to test  
✅ Security research, CTF challenges, authorized pentesting  
✅ Finding vulnerabilities before attackers do  

❌ Unauthorized testing is illegal in most jurisdictions  
❌ Do not target production systems without permission  
❌ Do not use to build malware or ransomware  

---

## Requirements

```
python 3.9+
anthropic>=0.18.0
rich>=13.0.0
```

---

## Tests

```bash
python -m pytest tests/
python tests/test_forge.py      # 53 tests
python tests/test_learn.py      # 21 tests
```

---

*Built in one conversation. One idea at a time. Still evolving.* ⚒️🔥
