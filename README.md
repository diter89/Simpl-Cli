
# Simpl-CLI: Multi-Persona AI Agent

## ⚠️ Development Status

**This is a PROTOTYPE/PROOF-OF-CONCEPT** project currently in active development. Features may be incomplete, unstable, or subject to major changes.

**Not recommended for production use.**

## Overview

Simpl-CLI is an experimental multi-persona AI agent framework that demonstrates advanced CLI interaction patterns through modular persona architecture, intelligent routing, and multi-modal memory systems.

## Key Features

- **Smart Router**: Intent-based routing with confidence scoring
- **Modular Personas**: Specialized agents for different tasks
- **Multi-Modal Memory**: ChromaDB vector storage + JSON session persistence
- **Web Intelligence**: Advanced scraping with fallback layers
- **Real-time Data**: Live market data, web content analysis

## Architecture

```
coreframe/          # Core routing & session management
├── advanced_router_full.py    # Intent classification & routing
├── session_manager_full.py    # Memory management
└── fireworks_api_client.py    # LLM integration

cores/              # Shared utilities
├── upgradescraper.py          # Web scraping engine
├── readle.py                  # Content extraction (BS4 + Trafilatura)
├── wallet_cache_handler.py    # API optimization
└── shared_console.py          # CLI presentation

pustakapersona/     # Persona implementations
├── personasearchweb_*.py      # Web search variants
├── personareadle.py           # URL content analysis
├── personawallet_analyze.py   # Financial data analysis
└── personacode.py             # Code generation
```

## Available Personas

| Persona | Purpose | Method |
|---------|---------|---------|
| **SearchWeb** | Web research & real-time data | Multi-query scraping with result validation |
| **Readle** | URL content analysis | 2-layer extraction (BS4 → Trafilatura fallback) |
| **Wallet** | Financial/crypto analysis | Custom API payload engineering |
| **CodeGen** | Code generation | Context-aware programming assistance |

## Memory Modes

1. **Linear Session**: Per-session JSON persistence
2. **ChromaDB Cross-Time**: Permanent vector storage with semantic search
3. **Continue Session**: Resume existing linear sessions

## Installation

```bash
git clone https://github.com/diter89/Simpl-Cli-tester
cd Simpl-Cli-tester
pip install -r requirements.txt
```

## Dependencies

```
beautifulsoup4==4.13.4
requests==2.32.4
inquirerpy==0.3.4
prompt_toolkit==3.0.51
rich==14.1.0
chromadb==1.0.15
Faker==37.4.2
trafilatura==2.0.0
```

## Usage

```bash
export FIREWORKS_API_KEY="<apikey>"
python3 app.py
```

Choose your preferred memory mode and start interacting with the agent.

## Example Interactions

```bash
# Web search with real-time data
~> find latest Bitcoin price and market analysis

# URL content analysis  
~> analyze this URL: https://example.com/article

# Cross-session memory recall
~> do you remember our previous discussion about AI frameworks?

# Code generation from analysis
~> convert this data into a FastAPI SSE endpoint
```
https://github.com/user-attachments/assets/6d2b1f97-aa75-4e92-8762-4481981bf2cc

## Current Limitations

- **Prototype Quality**: Code may contain rough edges and debug artifacts
- **API Dependencies**: Some features require external LLM API access
- **Scraping Reliability**: Web scraping may fail due to site changes
- **Limited Error Recovery**: Error handling is basic in current version
- **Performance**: Not optimized for high-concurrency usage

## Development Roadmap

**Next Iterations:**
- [ ] ML-based intent classification
- [ ] Enhanced error handling and recovery
- [ ] Configuration management system
- [ ] Performance optimization
- [ ] Comprehensive testing suite
- [ ] API rate limiting and monitoring
