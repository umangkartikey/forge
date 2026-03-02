#!/bin/bash
# ⚒️  FORGE — One-command installer

set -e

BOLD="\033[1m"; CYAN="\033[96m"; GREEN="\033[92m"; YELLOW="\033[93m"; RESET="\033[0m"

echo -e "${CYAN}${BOLD}"
echo "  ███████╗ ██████╗ ██████╗  ██████╗ ███████╗"
echo "  ██╔════╝██╔═══██╗██╔══██╗██╔════╝ ██╔════╝"
echo "  █████╗  ██║   ██║██████╔╝██║  ███╗█████╗  "
echo "  ██╔══╝  ██║   ██║██╔══██╗██║   ██║██╔══╝  "
echo "  ██║     ╚██████╔╝██║  ██║╚██████╔╝███████╗"
echo "  ╚═╝      ╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚══════╝"
echo -e "${RESET}"
echo -e "  ${BOLD}Framework for Orchestrated Reasoning & Generation of Engines${RESET}"
echo ""

# Check Python
echo -e "${CYAN}Checking Python...${RESET}"
if ! command -v python3 &>/dev/null; then
    echo -e "${YELLOW}Python 3 not found. Install from https://python.org${RESET}"; exit 1
fi
PYVER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo -e "  ${GREEN}✓${RESET} Python $PYVER"

# Install deps
echo -e "\n${CYAN}Installing dependencies...${RESET}"
pip install anthropic rich --quiet --break-system-packages 2>/dev/null || \
pip install anthropic rich --quiet

echo -e "  ${GREEN}✓${RESET} anthropic"
echo -e "  ${GREEN}✓${RESET} rich"

# Optional: paramiko for real SSH brute-force
read -p "  Install paramiko for SSH testing? (y/N) " -n 1 -r; echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    pip install paramiko --quiet --break-system-packages 2>/dev/null || pip install paramiko --quiet
    echo -e "  ${GREEN}✓${RESET} paramiko"
fi

# API key setup
echo -e "\n${CYAN}API Key Setup${RESET}"
if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo -e "  ${YELLOW}ANTHROPIC_API_KEY not set.${RESET}"
    read -p "  Enter your key (or press Enter to skip): " APIKEY
    if [ -n "$APIKEY" ]; then
        # Add to shell config
        SHELL_RC="$HOME/.bashrc"
        [[ "$SHELL" == *"zsh"* ]] && SHELL_RC="$HOME/.zshrc"
        echo "export ANTHROPIC_API_KEY=$APIKEY" >> "$SHELL_RC"
        export ANTHROPIC_API_KEY=$APIKEY
        echo -e "  ${GREEN}✓${RESET} Key saved to $SHELL_RC"
    fi
else
    echo -e "  ${GREEN}✓${RESET} ANTHROPIC_API_KEY already set"
fi

# Create dirs
mkdir -p forge_tools forge_learn forge_swarm/hive forge_swarm/workers
echo -e "  ${GREEN}✓${RESET} Directories created"

# Done
echo -e "\n${GREEN}${BOLD}✅  FORGE installed!${RESET}\n"
echo -e "  Run any of these:"
echo -e "  ${CYAN}python forge.py${RESET}         — Build AI tools"
echo -e "  ${CYAN}python forge_meta.py${RESET}    — Metasploit-style console"
echo -e "  ${CYAN}python forge_swarm.py${RESET}   — Self-replicating swarm"
echo -e "  ${CYAN}python forge_learn.py${RESET}   — Learning engine"
echo ""
