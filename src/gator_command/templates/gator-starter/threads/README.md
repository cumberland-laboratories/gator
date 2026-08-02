# Threads

Lightweight reference notes on topics that have momentum. Threads are shorter than artifacts — typically 5–20 lines — and track evolving ideas, design directions, or decisions-in-progress.

## When to create a thread

- A topic keeps coming up across sessions and needs a stable reference point
- A design direction is forming but isn't ready for a full artifact
- You want to capture context that would otherwise be lost between sessions

## How to create one

Ask your AI coding agent:

> "Create a thread about [topic] — capture what we've decided so far and what's still open."

Or during a session:

> "This discussion about [topic] has momentum. Save it as a thread."

## Active threads vs archived threads

- `active-threads/` — topics currently being worked on. Checked at session open.
- `threads/` — reference threads. Still useful, but not actively driving work.

When a thread's topic is resolved or paused, move it from `active-threads/` to `threads/`.

## What threads are not

Threads are not task lists (use roadmap), not deep analyses (use artifacts), and not one-line captures (use inbox). They are the middle layer — enough structure to be useful across sessions, lightweight enough to create without ceremony.
