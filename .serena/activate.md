

Set up your virtual environment
```
uv venv --python 3.12

# Mac
source .venv/bin/activate

# Windows
.venv\Scripts\activate
```

Install dependencies
```
uv pip install -U 'agno[os]' anthropic mcp
```

fastapi dev agno_agent.py