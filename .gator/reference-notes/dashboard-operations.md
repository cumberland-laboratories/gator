# Dashboard Operations

Notes on launching and operating the Gator Dashboard from an agent session.

## Launching

```
python src/gator_command/scripts/gator-dashboard.py
```

The script starts an HTTP server on port 8420, opens the browser, and enters `serve_forever()`. It works on the first invocation. Do not retry or attempt to verify the launch — the server process stays alive but agent tooling may incorrectly report it as completed because only the startup banner is captured before the event loop takes over.

**Known false signal**: background task tracking (Claude Code, other agent harnesses) can show the dashboard process as "completed" immediately after launch. This is a monitoring artifact, not a failure. The dashboard is running.

## Flags

| Flag | Effect |
|------|--------|
| `--no-open` | Start server without opening browser |
| `--port N` | Use a specific port (default 8420, tries 8421-8429 on conflict) |
| `--snapshot` | Write self-contained HTML to stdout and exit (no server) |
| `--repo NAME` | Pre-load a specific repo view on open |
