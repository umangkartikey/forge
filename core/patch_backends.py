#!/usr/bin/env python3
"""
Patches all FORGE files to use forge_core_ai.py as the universal backend.
Run once after adding forge_core_ai.py to your repo.

Usage: python patch_backends.py
"""

import re
from pathlib import Path

FILES = [
    "forge.py",
    "forge_meta.py",
    "forge_swarm.py",
    "forge_learn.py",
]

# The old pattern in every file
OLD_ANTHROPIC_BLOCK = re.compile(
    r"# ── Try anthropic ─+\n"
    r"try:.*?AI_AVAILABLE = False\n"
    r".*?AI_CLIENT\s*=\s*None\n",
    re.DOTALL
)

NEW_IMPORT = '''# ── AI Backend (universal — swap via FORGE_BACKEND env var) ──────────────────
try:
    from forge_core_ai import ai_call as _ai_call, ai_json, AI_AVAILABLE, ACTIVE_MODEL as MODEL, backend_info
    AI_CLIENT = True  # forge_core_ai manages the client internally
    def ai_call(prompt, system="You are a helpful assistant.", max_tokens=3000):
        return _ai_call(prompt, system, max_tokens)
except ImportError:
    AI_AVAILABLE = False
    AI_CLIENT    = None
    def ai_call(prompt, system="", max_tokens=3000): return None
    def ai_json(prompt, system="", max_tokens=2000): return None

'''

BOLD = "\033[1m"; G = "\033[92m"; Y = "\033[93m"; R = "\033[91m"; C = "\033[96m"; X = "\033[0m"

print(f"\n{C}{BOLD}⚒️  FORGE Backend Patcher{X}\n")

patched = 0
for fname in FILES:
    fp = Path(fname)
    if not fp.exists():
        print(f"  {Y}⚠️  Not found: {fname}{X}")
        continue

    src = fp.read_text()

    # Check if already patched
    if "forge_core_ai" in src:
        print(f"  {C}✓{X}  {fname} — already patched")
        continue

    # Find and replace the anthropic import block
    if "import anthropic" in src:
        # Replace try/except anthropic block
        new_src = re.sub(
            r"# ── Try anthropic ─+\ntry:\n.*?AI_CLIENT\s*=\s*None\n",
            NEW_IMPORT,
            src,
            flags=re.DOTALL
        )
        if new_src != src:
            fp.write_text(new_src)
            print(f"  {G}✅  {fname} — patched (replaced anthropic block){X}")
            patched += 1
        else:
            # Try simpler replacement
            new_src = src.replace(
                "import anthropic\n",
                "from forge_core_ai import ai_call, ai_json  # universal backend\n"
            )
            if new_src != src:
                fp.write_text(new_src)
                print(f"  {G}✅  {fname} — patched (simple import swap){X}")
                patched += 1
            else:
                print(f"  {Y}⚠️  {fname} — could not auto-patch, patch manually{X}")
    else:
        print(f"  {Y}?   {fname} — no anthropic import found{X}")

print(f"\n  {G}Done! {patched} file(s) patched.{X}")
print(f"\n  Now run FORGE with any backend:")
print(f"  {C}FORGE_BACKEND=ollama   FORGE_MODEL=llama3.1  python forge_swarm.py{X}")
print(f"  {C}FORGE_BACKEND=groq     GROQ_API_KEY=xxx       python forge_swarm.py{X}")
print(f"  {C}FORGE_BACKEND=custom   FORGE_BASE_URL=http://localhost:1234/v1  python forge.py{X}\n")
