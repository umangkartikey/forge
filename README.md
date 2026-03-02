# ⚒️ FORGE

**Framework for Orchestrated Reasoning & Generation of Engines**

> A self-replicating, self-building, self-learning AI security framework.  
> One Python file that copies itself, builds its own tools, and gets smarter every run.

<p align="center">
  <img src="docs/forge_banner.txt" alt="FORGE" />
</p>

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Ethical Use Only](https://img.shields.io/badge/use-ethical%20only-green.svg)](#ethics)

---

## What is FORGE?

FORGE is not a typical security tool. It's a **cognitive architecture** — an AI system that:

- 🔨 **Builds its own tools** on the fly based on what it discovers
- 🧬 **Replicates itself** into parallel worker instances
- 🐝 **Runs as a swarm** — multiple copies attacking a target simultaneously  
- 🧠 **Shares a hive mind** — findings and new tools propagate to all workers instantly
- 📚 **Learns from every run** — gets measurably smarter over time via SQLite brain
- 🔁 **Evolves its own prompts** — genetic algorithm rewrites its own thinking
  
## LLM Pentesting
FORGE can audit AI systems themselves:
- Prompt injection testing
- System prompt extraction  
- RAG pipeline data leakage
- Agent hijacking via indirect injection
- Jailbreak enumeration
---
# 🟣 Claude (default, no change needed)
python forge_swarm.py

# 🦙 Llama locally — FREE, completely private
FORGE_BACKEND=ollama FORGE_MODEL=llama3.1 python forge_swarm.py

# 🔥 DeepSeek for code tasks — best open source coder
FORGE_BACKEND=ollama FORGE_MODEL=deepseek-coder-v2 python forge_swarm.py

# ⚡ Groq — insanely fast, free tier
FORGE_BACKEND=groq GROQ_API_KEY=xxx python forge_swarm.py

# 🌊 Any other model on Together.ai
FORGE_BACKEND=together FORGE_MODEL=Qwen/Qwen2-72B-Instruct python forge_swarm.py

# 🔥 LM Studio / Jan / anything local
FORGE_BACKEND=custom FORGE_BASE_URL=http://localhost:1234/v1 python forge_swarm.py

## Quick Start

```bash
# In your repo, update README.md line:
git clone https://github.com/umangkartikey/forge
cd forge
pip install -r requirements.txt
export ANTHROPIC_API_KEY=your_key_here
python forge.py
```

---

## Architecture

```
FORGE/
├── forge.py              # 🔨 Core builder — build/improve/remix/test tools
├── forge_meta.py         # 🎯 Metasploit-style console — use/set/run modules
├── forge_swarm.py        # 🐝 Self-replicating swarm — parallel hive mind
├── forge_learn.py        # 📚 Learning engine — SQLite brain, pattern evolution
│
├── core/                 # Core shared utilities
│   ├── hive.py           # Hive mind message bus
│   ├── registry.py       # Tool/module registry
│   └── ai.py             # AI client wrapper
│
├── modules/              # Built-in security modules
│   ├── scanner/
│   ├── recon/
│   ├── cracker/
│   └── util/
│
├── learn/                # Learning system
│   ├── brain.db          # SQLite persistent memory (auto-created)
│   ├── patterns.json     # Extracted attack patterns
│   └── evolved_prompts/  # AI-rewritten prompts
│
├── swarm/                # Swarm worker instances (auto-created)
│   └── hive/             # Shared hive mind state
│
└── tests/
    ├── test_forge.py      # 53 tests, 100% pass rate
    └── test_swarm.py
```

---

## Modes

### 1. Build Mode — `forge.py`
```bash
python forge.py
# FORGE > build a port scanner with banner grabbing
# FORGE > genetic         # evolve best version via natural selection
# FORGE > ai2ai           # 5 AI agents debate and refine the tool
# FORGE > autopilot       # fully autonomous goal execution
```

### 2. Meta Console — `forge_meta.py`
```bash
python forge_meta.py
# forge-meta > use scanner/portscan
# forge-meta > set TARGET 192.168.1.1
# forge-meta > run
# forge-meta > nl scan 192.168.1.1 for open ports    # natural language
# forge-meta > map 192.168.1.1                        # full surface map
# forge-meta > autopilot 192.168.1.1                  # full autonomous
```

### 3. Swarm Mode — `forge_swarm.py`
```bash
python forge_swarm.py
# forge-swarm > swarm 192.168.1.0/24
# → AI decomposes into 8 parallel tasks
# → FORGE copies itself × 8
# → All instances run simultaneously
# → Hive mind shares findings in real-time
# → New modules built by any worker sync to all others
# → Unified report generated
```

### 4. Learning Mode — `forge_learn.py`
```bash
python forge_learn.py
# forge-learn > status     # view what FORGE has learned
# forge-learn > patterns   # show discovered attack patterns
# forge-learn > evolve     # run genetic algo on system prompts
# forge-learn > replay     # re-run best performing strategies
```

---

## The Learning Loop

```
Run → Capture → Rate → Extract → Evolve → Next run is smarter

Every swarm run:
  ① Captures: modules run, findings, timings, success rates
  ② Rates:    AI scores each finding (signal vs noise)
  ③ Extracts: "Redis always exposed on internal /24 networks"
  ④ Evolves:  rewrites planner prompts with learned patterns
  ⑤ Result:   next run starts smarter, plans better, finds more
```

The brain lives in `learn/brain.db` — a SQLite database that persists forever across all runs. Every target, every finding, every module build is recorded and used to improve future performance.

---

## Built-in Modules

| Module | Category | Description |
|--------|----------|-------------|
| `scanner/portscan` | Scanner | Multi-threaded TCP scanner with banner grabbing |
| `recon/http` | Recon | HTTP security headers, tech stack, directory enum |
| `recon/osint` | Recon | DNS, WHOIS, subdomain discovery |
| `recon/network` | Recon | Local network interfaces, listening ports |
| `brute/ssh` | Brute | SSH login brute-forcer (your systems only) |
| `cracker/hash` | Cracker | MD5/SHA1/SHA256/SHA512 dictionary attack |
| `util/passgen` | Utility | Cryptographically secure password generator |

Plus any modules the swarm builds at runtime — these go into `modules/pool/` and are shared across all instances.

---

## Hive Mind

When running in swarm mode, all FORGE instances share a file-based message bus:

```
forge_swarm/hive/
├── bus.json        # real-time message bus (findings, module builds, status)
├── memory.json     # aggregated findings from all workers
├── modules.json    # module registry shared across swarm
└── status.json     # live worker progress map
```

When **any worker builds a new module**, it's instantly available to all other workers. The swarm collectively builds a tool library that grows with every run.

---

## Ethics

FORGE is built for:
- ✅ Security research on systems you own
- ✅ CTF challenges
- ✅ Learning networking and security concepts
- ✅ Authorized penetration testing

FORGE will not:
- ❌ Build actual malware or ransomware
- ❌ Target systems without permission
- ❌ Generate exploit code for known CVEs against production systems

The AI safety layer checks all generated modules and refuses unsafe requests.

---

## Requirements

```
python 3.9+
anthropic>=0.18.0
rich>=13.0.0
```

Optional:
```
paramiko    # for real SSH brute-force (otherwise demo mode)
```

---

## Contributing

Modules are the easiest way to contribute. Any `.py` file in `modules/` following the format gets auto-loaded:

```python
# MODULE_NAME: your_module
# CATEGORY: scanner|recon|cracker|util
# DESCRIPTION: What it does
# OPTIONS: TARGET=localhost:Target host, PORT=80:Port number

def run(options, session, workspace):
    target = options.get("TARGET", "localhost")
    # ... your code ...
    return {"status": "success", "output": "result", "data": {...}}
```

---

## License

MIT — see [LICENSE](LICENSE)

---

*Built in one conversation. Grown from one idea. Still evolving.* ⚒️🔥
