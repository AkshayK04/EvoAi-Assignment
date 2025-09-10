# EvoAI Assignment — Agentic Commerce (LangGraph)

Self-contained LangGraph-style agent with product assist + strict 60-minute cancellation policy.  
Deterministic tests produce trace JSON + final replies.

## Setup (Python)
```bash
uv venv && uv pip install -r requirements.txt
python -m tests.run_tests
