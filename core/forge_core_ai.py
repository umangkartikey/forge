#!/usr/bin/env python3
"""
⚒️  FORGE CORE AI — Universal Model Backend
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Drop-in replacement for all AI calls across FORGE.
Switch any model via environment variables. Zero code changes.

Supported backends:
  🟣  anthropic   — Claude (default)
  🦙  ollama      — Local models (Llama, Mistral, DeepSeek, Phi...)
  ⚡  groq        — Ultra-fast inference (free tier available)
  🟢  openai      — GPT-4o, GPT-4-turbo
  🌊  together    — Together.ai (100+ open models)
  🤗  huggingface — HuggingFace Inference API
  🔷  cohere      — Cohere Command
  🔥  custom      — Any OpenAI-compatible endpoint

Usage:
  # Anthropic (default)
  python forge_swarm.py

  # Ollama local (free, private)
  FORGE_BACKEND=ollama FORGE_MODEL=llama3.1 python forge_swarm.py

  # Groq (fast, free tier)
  FORGE_BACKEND=groq FORGE_MODEL=llama-3.1-70b-versatile python forge_swarm.py

  # Together.ai
  FORGE_BACKEND=together FORGE_MODEL=meta-llama/Llama-3-70b-chat-hf python forge_swarm.py

  # Any OpenAI-compatible API
  FORGE_BACKEND=custom FORGE_BASE_URL=http://localhost:1234/v1 FORGE_MODEL=local-model python forge_swarm.py

Environment variables:
  FORGE_BACKEND       — backend name (default: anthropic)
  FORGE_MODEL         — model name (auto-selected per backend if not set)
  FORGE_BASE_URL      — custom API base URL (for custom/ollama backends)
  FORGE_API_KEY       — API key (falls back to backend-specific env vars)
  FORGE_MAX_RETRIES   — retries on JSON parse failure (default: 3)
  FORGE_TIMEOUT       — request timeout seconds (default: 60)
  FORGE_TEMPERATURE   — model temperature (default: 0.7)
  ANTHROPIC_API_KEY   — Anthropic key
  GROQ_API_KEY        — Groq key
  OPENAI_API_KEY      — OpenAI key
  TOGETHER_API_KEY    — Together.ai key
  HF_API_KEY          — HuggingFace key
  COHERE_API_KEY      — Cohere key
"""

import os, re, json, time, sys
from pathlib import Path

# ── Config from environment ───────────────────────────────────────────────────

BACKEND     = os.environ.get("FORGE_BACKEND",     "anthropic").lower()
MODEL       = os.environ.get("FORGE_MODEL",       "")
BASE_URL    = os.environ.get("FORGE_BASE_URL",    "")
API_KEY     = os.environ.get("FORGE_API_KEY",     "")
MAX_RETRIES = int(os.environ.get("FORGE_MAX_RETRIES", "3"))
TIMEOUT     = int(os.environ.get("FORGE_TIMEOUT",     "60"))
TEMPERATURE = float(os.environ.get("FORGE_TEMPERATURE","0.7"))

# ── Default models per backend ────────────────────────────────────────────────

DEFAULT_MODELS = {
    "anthropic":   "claude-sonnet-4-6",
    "ollama":      "llama3.1",
    "groq":        "llama-3.1-70b-versatile",
    "openai":      "gpt-4o",
    "together":    "meta-llama/Llama-3-70b-chat-hf",
    "huggingface": "mistralai/Mistral-7B-Instruct-v0.2",
    "cohere":      "command-r-plus",
    "custom":      "local-model",
}

ACTIVE_MODEL = MODEL or DEFAULT_MODELS.get(BACKEND, "unknown")

# ── Colors for terminal output ────────────────────────────────────────────────
C="\033[96m"; Y="\033[93m"; G="\033[92m"; R="\033[91m"; M="\033[95m"
DIM="\033[2m"; X="\033[0m"; BOLD="\033[1m"

# ══════════════════════════════════════════════════════════════════════════════
# 🔧 BACKEND IMPLEMENTATIONS
# ══════════════════════════════════════════════════════════════════════════════

def _call_anthropic(prompt, system, max_tokens):
    import anthropic
    key    = API_KEY or os.environ.get("ANTHROPIC_API_KEY","")
    client = anthropic.Anthropic(api_key=key) if key else anthropic.Anthropic()
    r = client.messages.create(
        model      = ACTIVE_MODEL,
        max_tokens = max_tokens,
        system     = system,
        messages   = [{"role":"user","content":prompt}]
    )
    return r.content[0].text

def _call_ollama(prompt, system, max_tokens):
    """Ollama local inference — tries SDK first, falls back to HTTP."""
    model = ACTIVE_MODEL
    base  = BASE_URL or "http://localhost:11434"

    # Try ollama SDK
    try:
        import ollama as ol
        r = ol.chat(
            model    = model,
            messages = [
                {"role":"system",  "content": system},
                {"role":"user",    "content": prompt},
            ],
            options  = {"num_predict": max_tokens, "temperature": TEMPERATURE}
        )
        return r["message"]["content"]
    except ImportError:
        pass

    # Fallback to raw HTTP (no extra deps needed)
    import urllib.request, urllib.error
    payload = json.dumps({
        "model":    model,
        "messages": [
            {"role":"system", "content": system},
            {"role":"user",   "content": prompt},
        ],
        "stream": False,
        "options": {"num_predict": max_tokens, "temperature": TEMPERATURE}
    }).encode()

    req  = urllib.request.Request(
        f"{base}/api/chat",
        data    = payload,
        headers = {"Content-Type":"application/json"},
        method  = "POST"
    )
    resp = urllib.request.urlopen(req, timeout=TIMEOUT)
    data = json.loads(resp.read())
    return data["message"]["content"]

def _call_groq(prompt, system, max_tokens):
    key = API_KEY or os.environ.get("GROQ_API_KEY","")
    try:
        from groq import Groq
        client = Groq(api_key=key)
        r = client.chat.completions.create(
            model      = ACTIVE_MODEL,
            max_tokens = max_tokens,
            temperature= TEMPERATURE,
            messages   = [
                {"role":"system", "content": system},
                {"role":"user",   "content": prompt},
            ]
        )
        return r.choices[0].message.content
    except ImportError:
        # Fallback HTTP (Groq is OpenAI-compatible)
        return _call_openai_compat(
            prompt, system, max_tokens,
            base_url = "https://api.groq.com/openai/v1",
            api_key  = key
        )

def _call_openai(prompt, system, max_tokens):
    key = API_KEY or os.environ.get("OPENAI_API_KEY","")
    return _call_openai_compat(prompt, system, max_tokens,
                               base_url = "https://api.openai.com/v1",
                               api_key  = key)

def _call_together(prompt, system, max_tokens):
    key = API_KEY or os.environ.get("TOGETHER_API_KEY","")
    return _call_openai_compat(prompt, system, max_tokens,
                               base_url = "https://api.together.xyz/v1",
                               api_key  = key)

def _call_huggingface(prompt, system, max_tokens):
    """HuggingFace Inference API."""
    key   = API_KEY or os.environ.get("HF_API_KEY","")
    model = ACTIVE_MODEL
    url   = f"https://api-inference.huggingface.co/models/{model}/v1/chat/completions"

    return _call_openai_compat(prompt, system, max_tokens,
                               base_url = f"https://api-inference.huggingface.co/models/{model}/v1",
                               api_key  = key)

def _call_cohere(prompt, system, max_tokens):
    key = API_KEY or os.environ.get("COHERE_API_KEY","")
    try:
        import cohere
        client = cohere.Client(api_key=key)
        r = client.chat(
            model       = ACTIVE_MODEL,
            preamble    = system,
            message     = prompt,
            max_tokens  = max_tokens,
            temperature = TEMPERATURE,
        )
        return r.text
    except ImportError:
        # Fallback HTTP
        import urllib.request
        payload = json.dumps({
            "model":       ACTIVE_MODEL,
            "preamble":    system,
            "message":     prompt,
            "max_tokens":  max_tokens,
            "temperature": TEMPERATURE,
        }).encode()
        req = urllib.request.Request(
            "https://api.cohere.ai/v1/chat",
            data    = payload,
            headers = {"Content-Type":"application/json","Authorization":f"Bearer {key}"},
            method  = "POST"
        )
        resp = urllib.request.urlopen(req, timeout=TIMEOUT)
        return json.loads(resp.read())["text"]

def _call_custom(prompt, system, max_tokens):
    """Any OpenAI-compatible endpoint."""
    key  = API_KEY or os.environ.get("OPENAI_API_KEY","") or "none"
    base = BASE_URL or "http://localhost:1234/v1"
    return _call_openai_compat(prompt, system, max_tokens,
                               base_url=base, api_key=key)

def _call_openai_compat(prompt, system, max_tokens, base_url, api_key):
    """Generic OpenAI-compatible HTTP call — no SDK needed."""
    import urllib.request

    payload = json.dumps({
        "model":       ACTIVE_MODEL,
        "max_tokens":  max_tokens,
        "temperature": TEMPERATURE,
        "messages": [
            {"role":"system", "content": system},
            {"role":"user",   "content": prompt},
        ]
    }).encode()

    headers = {
        "Content-Type":  "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    req  = urllib.request.Request(
        f"{base_url}/chat/completions",
        data    = payload,
        headers = headers,
        method  = "POST"
    )
    resp = urllib.request.urlopen(req, timeout=TIMEOUT)
    data = json.loads(resp.read())
    return data["choices"][0]["message"]["content"]

# ── Backend router ────────────────────────────────────────────────────────────

BACKENDS = {
    "anthropic":   _call_anthropic,
    "ollama":      _call_ollama,
    "groq":        _call_groq,
    "openai":      _call_openai,
    "together":    _call_together,
    "huggingface": _call_huggingface,
    "hf":          _call_huggingface,
    "cohere":      _call_cohere,
    "custom":      _call_custom,
    "local":       _call_custom,
}

# ══════════════════════════════════════════════════════════════════════════════
# 🎯 MAIN INTERFACE — Drop-in replacement for all forge ai_call() functions
# ══════════════════════════════════════════════════════════════════════════════

def ai_call(prompt, system="You are a helpful assistant.", max_tokens=3000):
    """
    Universal AI call. Works with any configured backend.
    Drop-in replacement for all forge ai_call() implementations.
    """
    fn = BACKENDS.get(BACKEND)
    if not fn:
        available = ", ".join(BACKENDS.keys())
        raise ValueError(f"Unknown backend: '{BACKEND}'. Available: {available}")

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            result = fn(prompt, system, max_tokens)
            if result:
                return result.strip()
        except Exception as e:
            last_error = e
            if attempt < MAX_RETRIES:
                time.sleep(attempt * 1.5)  # exponential backoff
            continue

    # All retries failed
    print(f"{R}AI call failed after {MAX_RETRIES} attempts: {last_error}{X}")
    return None

def ai_json(prompt, system="Reply only with valid JSON.", max_tokens=2000):
    """
    AI call that guarantees a parsed dict/list back.
    Retries with stronger JSON instruction if parsing fails.
    """
    json_system = system + "\nIMPORTANT: Reply ONLY with valid JSON. No markdown, no explanation, no backticks."

    for attempt in range(MAX_RETRIES):
        result = ai_call(prompt, json_system if attempt > 0 else system, max_tokens)
        if not result:
            continue

        # Try to parse
        parsed = _safe_json(result)
        if parsed is not None:
            return parsed

        # Retry with stricter instruction
        json_system = "You MUST reply with ONLY valid JSON. Nothing else. No text before or after."

    return None

def ai_stream(prompt, system="You are a helpful assistant.", max_tokens=3000, callback=None):
    """
    Streaming AI call. Falls back to regular call if streaming not supported.
    callback(chunk) is called for each text chunk.
    """
    if BACKEND == "anthropic":
        try:
            import anthropic
            key    = API_KEY or os.environ.get("ANTHROPIC_API_KEY","")
            client = anthropic.Anthropic(api_key=key) if key else anthropic.Anthropic()
            full   = ""
            with client.messages.stream(
                model=ACTIVE_MODEL, max_tokens=max_tokens, system=system,
                messages=[{"role":"user","content":prompt}]
            ) as stream:
                for chunk in stream.text_stream:
                    full += chunk
                    if callback: callback(chunk)
                    else: print(chunk, end="", flush=True)
            return full
        except Exception as e:
            print(f"\n{Y}Stream failed ({e}), falling back to regular call{X}")

    elif BACKEND == "ollama":
        try:
            import ollama as ol
            full = ""
            for chunk in ol.chat(
                model    = ACTIVE_MODEL,
                messages = [{"role":"system","content":system},{"role":"user","content":prompt}],
                stream   = True,
                options  = {"num_predict":max_tokens,"temperature":TEMPERATURE}
            ):
                text = chunk["message"]["content"]
                full += text
                if callback: callback(text)
                else: print(text, end="", flush=True)
            return full
        except Exception as e:
            print(f"\n{Y}Ollama stream failed ({e}){X}")

    # Fallback — regular call
    result = ai_call(prompt, system, max_tokens)
    if result:
        if callback: callback(result)
        else: print(result)
    return result

# ══════════════════════════════════════════════════════════════════════════════
# 🛠️ UTILITIES
# ══════════════════════════════════════════════════════════════════════════════

def _safe_json(text):
    """Try every strategy to extract JSON from AI response."""
    if not text: return None

    # Strip markdown code blocks (handles ```json, ```python, ``` etc)
    text = re.sub(r"```[a-z]*", "", text)
    text = text.replace("```", "").strip()

    # Direct parse
    try: return json.loads(text)
    except: pass

    # Find first complete JSON object
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try: return json.loads(m.group())
        except: pass

    # Find first JSON array
    m = re.search(r"\[.*\]", text, re.DOTALL)
    if m:
        try: return json.loads(m.group())
        except: pass

    return None

def check_backend():
    """Test if the current backend is reachable and working."""
    print(f"\n{C}{BOLD}⚒️  FORGE AI Backend Check{X}")
    print(f"  Backend:  {Y}{BACKEND}{X}")
    print(f"  Model:    {Y}{ACTIVE_MODEL}{X}")
    if BASE_URL: print(f"  Base URL: {DIM}{BASE_URL}{X}")
    print()

    # Quick connectivity test
    print(f"  {DIM}Testing connection...{X}", end="", flush=True)
    result = ai_call("Say only: OK", "Reply with the single word OK.", max_tokens=10)
    if result and "ok" in result.lower():
        print(f"\r  {G}✅  Connected! Response: {result.strip()}{X}")
        return True
    elif result:
        print(f"\r  {Y}⚠️  Connected but unexpected response: {result[:50]}{X}")
        return True
    else:
        print(f"\r  {R}❌  Connection failed.{X}")
        return False

def list_ollama_models():
    """List models available in local Ollama."""
    import urllib.request
    try:
        base = BASE_URL or "http://localhost:11434"
        resp = urllib.request.urlopen(f"{base}/api/tags", timeout=5)
        data = json.loads(resp.read())
        models = [m["name"] for m in data.get("models",[])]
        return models
    except:
        return []

def pull_ollama_model(model_name):
    """Pull a model into Ollama."""
    print(f"  {C}Pulling {model_name} into Ollama...{X}")
    result = os.system(f"ollama pull {model_name}")
    return result == 0

def backend_info():
    """Return info dict about the current backend configuration."""
    return {
        "backend":     BACKEND,
        "model":       ACTIVE_MODEL,
        "base_url":    BASE_URL or "(default)",
        "max_retries": MAX_RETRIES,
        "timeout":     TIMEOUT,
        "temperature": TEMPERATURE,
    }

# ══════════════════════════════════════════════════════════════════════════════
# 📋 SETUP GUIDE — Printed when run directly
# ══════════════════════════════════════════════════════════════════════════════

SETUP_GUIDES = {
    "ollama": f"""
  {C}{BOLD}🦙 Ollama Setup (Free, Local, Private){X}

  1. Install Ollama:
     {Y}curl https://ollama.ai/install.sh | sh{X}

  2. Pull a model:
     {Y}ollama pull llama3.1{X}          # 8B, good balance
     {Y}ollama pull deepseek-coder-v2{X}  # best for code
     {Y}ollama pull mistral{X}            # fast and light
     {Y}ollama pull phi3{X}               # tiny, runs anywhere

  3. Run FORGE with Ollama:
     {Y}FORGE_BACKEND=ollama FORGE_MODEL=llama3.1 python forge_swarm.py{X}

  {DIM}No API key needed. Runs 100% on your machine.{X}
""",
    "groq": f"""
  {C}{BOLD}⚡ Groq Setup (Fast, Free Tier){X}

  1. Get free API key: {Y}https://console.groq.com{X}

  2. Install SDK (optional):
     {Y}pip install groq{X}

  3. Run FORGE with Groq:
     {Y}FORGE_BACKEND=groq \\
     GROQ_API_KEY=your_key \\
     FORGE_MODEL=llama-3.1-70b-versatile \\
     python forge_swarm.py{X}

  Available models:
     {DIM}llama-3.1-70b-versatile  (best)
     llama-3.1-8b-instant     (fastest)
     mixtral-8x7b-32768       (long context)
     gemma2-9b-it             (Google){X}
""",
    "together": f"""
  {C}{BOLD}🌊 Together.ai Setup (100+ Models){X}

  1. Get API key: {Y}https://api.together.xyz{X}

  2. Run FORGE:
     {Y}FORGE_BACKEND=together \\
     TOGETHER_API_KEY=your_key \\
     FORGE_MODEL=meta-llama/Llama-3-70b-chat-hf \\
     python forge_swarm.py{X}

  Popular models:
     {DIM}meta-llama/Llama-3-70b-chat-hf
     mistralai/Mixtral-8x7B-Instruct-v0.1
     deepseek-ai/deepseek-coder-33b-instruct
     Qwen/Qwen2-72B-Instruct{X}
""",
    "custom": f"""
  {C}{BOLD}🔥 Custom Endpoint Setup{X}

  Works with any OpenAI-compatible API:
     {DIM}LM Studio, Jan, llama.cpp server,
     vLLM, text-generation-webui, etc.{X}

  Run FORGE:
     {Y}FORGE_BACKEND=custom \\
     FORGE_BASE_URL=http://localhost:1234/v1 \\
     FORGE_MODEL=your-model-name \\
     python forge_swarm.py{X}
""",
}

def main():
    print(f"""
{C}{BOLD}
  ⚒️  FORGE CORE AI — Universal Model Backend
{'━'*50}
{X}
  Current config:
    Backend:     {Y}{BACKEND}{X}
    Model:       {Y}{ACTIVE_MODEL}{X}
    Retries:     {DIM}{MAX_RETRIES}{X}
    Timeout:     {DIM}{TIMEOUT}s{X}
    Temperature: {DIM}{TEMPERATURE}{X}
""")

    import sys
    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()

        if cmd == "check":
            check_backend()

        elif cmd == "setup":
            backend = sys.argv[2].lower() if len(sys.argv) > 2 else BACKEND
            guide   = SETUP_GUIDES.get(backend)
            if guide: print(guide)
            else:
                print(f"  {Y}No setup guide for: {backend}{X}")
                print(f"  Available: {', '.join(SETUP_GUIDES.keys())}")

        elif cmd == "models" and BACKEND == "ollama":
            models = list_ollama_models()
            if models:
                print(f"  {G}Ollama models installed:{X}")
                for m in models: print(f"    {DIM}●{X}  {m}")
            else:
                print(f"  {Y}No models found. Is Ollama running?{X}")
                print(f"  {DIM}Start: ollama serve{X}")

        elif cmd == "pull" and len(sys.argv) > 2:
            pull_ollama_model(sys.argv[2])

        elif cmd == "backends":
            print(f"  {C}Available backends:{X}\n")
            info = [
                ("anthropic",   "Claude Sonnet/Opus/Haiku",           "ANTHROPIC_API_KEY"),
                ("ollama",      "Local models (Llama, Mistral, etc.)", "none needed"),
                ("groq",        "Ultra-fast inference, free tier",     "GROQ_API_KEY"),
                ("openai",      "GPT-4o, GPT-4-turbo",                 "OPENAI_API_KEY"),
                ("together",    "100+ open models",                    "TOGETHER_API_KEY"),
                ("huggingface", "HuggingFace Inference API",           "HF_API_KEY"),
                ("cohere",      "Command R+",                          "COHERE_API_KEY"),
                ("custom",      "Any OpenAI-compatible endpoint",      "optional"),
            ]
            for name, desc, key_var in info:
                active = f" {G}← active{X}" if name == BACKEND else ""
                print(f"  {Y}{name:<14}{X} {desc:<40} {DIM}{key_var}{X}{active}")

        else:
            print(f"  Commands:")
            print(f"    {Y}python forge_core_ai.py check{X}           — test connection")
            print(f"    {Y}python forge_core_ai.py backends{X}        — list all backends")
            print(f"    {Y}python forge_core_ai.py setup ollama{X}    — setup guide")
            print(f"    {Y}python forge_core_ai.py models{X}          — list ollama models")
            print(f"    {Y}python forge_core_ai.py pull llama3.1{X}   — pull ollama model")

    else:
        # No args — run check
        check_backend()
        print(f"""
  {C}Switch backends:{X}
    {DIM}FORGE_BACKEND=ollama   FORGE_MODEL=llama3.1          python forge.py
    FORGE_BACKEND=groq     FORGE_MODEL=llama-3.1-70b      python forge.py
    FORGE_BACKEND=together FORGE_MODEL=Qwen/Qwen2-72B      python forge.py
    FORGE_BACKEND=custom   FORGE_BASE_URL=http://localhost  python forge.py{X}

  {DIM}python forge_core_ai.py setup ollama    — Ollama setup guide
  python forge_core_ai.py backends          — all backends{X}
""")

if __name__ == "__main__":
    main()
