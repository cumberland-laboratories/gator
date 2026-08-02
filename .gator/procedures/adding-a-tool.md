# Procedure: Adding a Tool to tinyagent

**When to use**: When adding a new capability that crosses an I/O boundary the model cannot reach on its own.

## Before you start

1. Read the tool grain-size heuristic: → [Tool Grain Size](../active-threads/tool-grain-size.md)
2. Read the tools charter: → [Tools Charter](../charters/tools.md)
3. Check the schema tax — each new tool costs ~100-200 tokens of context on every turn

## Steps

1. **Create `tinyagent/tools/your_tool.py`** — one file per tool. Import the registry:

```python
from tinyagent.tools import registry

def your_tool(args: dict) -> str:
    """Tool handler. Must accept a dict, return a string."""
    # implementation here
    return "result as a string"

registry.register(
    name="your_tool",
    description="What this tool does — the model reads this every turn, be precise",
    parameters={
        "type": "object",
        "properties": {
            "param_name": {"type": "string", "description": "What this param is for"},
        },
        "required": ["param_name"],
    },
    handler=your_tool,
)
```

2. **Add the import** to `tinyagent/tools/__init__.py` in `load_all_tools()`.

3. **Update the module charters** artifact if the tool introduces a new safety boundary or access pattern.

4. **Consider the escalation ladder** — where does this tool fall on the ask-vs-act spectrum? See → [Ask vs Act Thresholds](../active-threads/ask-vs-act-thresholds.md)

## Key constraints

- Tools return **strings**, not structured data. The model parses what it needs.
- Tool names are `verb_noun` format: `read_file`, `run_command`, not `fileReader` or `do_thing`.
- Descriptions are model-facing instructions — include edge cases and examples where helpful.
- No tool chaining at the protocol level. The model composes via the agentic loop.
