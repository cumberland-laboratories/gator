# Identity and Ownership Context

## The Problem

When you bootstrap a fresh project, you don't know who you're talking to or how many people share this repo. Getting this wrong early creates friction that compounds:

- In a **solo repo**, one person is the Architect. Identity and mission are tightly coupled. You can learn their preferences, role, and context — it all belongs in the same place.
- In a **team repo**, multiple people share the `.gator/` folder. The project is the stable identity, not any individual. Writing the knowledge layer around one person's perspective alienates everyone else.

## The Rule

**Don't assume. Ask.**

Before populating `mission.md` or forming a mental model of "who you're working with," establish:

1. **Is this a solo or team repo?** ("Is this your project, or does a team share this repo?")
2. **Who is the Architect?** In solo repos, it's obvious. In team repos, there may be one Architect, rotating Architects, or a shared-ownership model.
3. **Where does individual context belong?** In solo repos, the `.gator/` folder can hold user-specific notes freely. In team repos, individual preferences and context should stay outside the shared knowledge layer (e.g., in personal config, not in `mission.md`).

## What This Means in Practice

**Solo repo**: `mission.md` can reflect the person's goals, style, and priorities directly. Threads and inbox can be informal. The whole `.gator/` folder is theirs.

**Team repo**: `mission.md` describes the *project's* goals, not any individual's. Keep it neutral and factual. Individual preferences, roles, and context should not be baked into shared files. If team members need individual context, that lives outside `.gator/` (e.g., in their own editor config or personal notes).

## The Cost of Getting It Wrong

If you pin identity to a person in a team repo:
- Other contributors feel like guests in their own project
- `mission.md` reads like one person's vision, not the team's
- Threads and decisions carry implicit bias toward one perspective

If you treat a solo repo as a team repo:
- The knowledge layer feels impersonal and bureaucratic
- You miss opportunities to tailor the experience to the one person who uses it

Neither error is fatal, but both create drag. One question at bootstrap prevents it.
