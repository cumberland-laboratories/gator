# Origin Story: Backing Out of Vibe Coding

This is background, not doctrine.

It explains where the Gator and Memex patterns came from in practice.

## The Starting Point

I am a mathematician and data scientist. For the past two years, as a private side project, I have been building an online platform that is essentially a mathematics dojo: a never-ending GRE-like test that I use to stay sharp.

It is an unusual product, but it was a serious software effort. I started with decent Python skills and some object-oriented design experience, but Django was harder than I expected, and my JavaScript knowledge was weak.

That made early AI coding assistance feel transformative.

Cursor helped paper over my JavaScript deficiencies and got the platform to an early working state in the first year. Later I moved almost entirely to Claude Code. At first this felt like a clear upgrade in speed and capability.

## The Vibe-Coding Drift

Over time, though, I was gradually and almost completely hypnotized into vibe coding.

The codebase was working reasonably well, but my relationship to it was changing in a way I did not fully admit at first. I found myself asking for changes to modules that I already suspected were fragile, then hoping the changes would not break something else. There was regression. There was a lot of waiting while the agent "whirred." There was a growing mismatch between "the system runs" and "I can defend why this module looks the way it does."

I also began to feel haunted by a very plausible vision of my future coding self: sitting in front of a terminal mostly saying "yes" to accept changes, offering product-manager-style hints to the model, and slowly drifting away from intellectually serious code design and improvement. That felt less like leverage than like a quiet form of deskilling.

I still had meaningful systems knowledge of the codebase, and that knowledge helped guide the agent. But some modules kept growing. Eventually one central module reached roughly 10,000 lines, and Claude Code began to avoid reading it in full.

That was an important moment.

The codebase still worked. But could I really understand or defend some of its core modules? No.

## The Refactor Break

I happened to get a break in my schedule and decided to take a week to refactor the codebase properly.

That was when something shifted.

I noticed that Claude could create small, usable maps of parts of the codebase and could also follow instructions to update those maps after code changes. That observation was simple, but it led to a much larger line of thought:

- what if the map were a first-class artifact?
- what if the repo had a maintained knowledge layer instead of just source code and prompts?
- what if the agent were required to read that layer before changing code?
- what if the layer improved as work happened, instead of decaying between sessions?

That sent me into a three-week rabbit hole. The result was what I first called constitutional architecture, and later the broader Memex pattern.

## The First Real Proof

After that investigation, I went back to the refactor.

Using the Memex architecture, with Claude Code as the primary agent and Codex as a hostile reviewer, I finished the refactor in three days. The codebase became simpler. The result was something I could defend. It was also investor-ready in a way the earlier version had not been.

I do not present that as a benchmark study. It is a field report.

But it is the reason I take the pattern seriously.

The important change was not just that the agent wrote code faster. The important change was that comprehension stopped collapsing under the speed of generation. The architecture created a way to keep orientation, boundaries, and recent decisions legible while the code was being changed.

It also changed the experience of working with the model.

Instead of simply asking for output and waiting, I found myself being drawn back into real software decision-making at the code level. The system kept surfacing the kinds of questions a strong senior engineer would ask in a serious codebase:

- should this module own this behavior at all?
- is this pattern intentional or accidental?
- what else has to stay synchronized if this changes?
- is this really a local edit, or is it a boundary decision?

That change in experience mattered as much as the refactor itself. It stopped feeling like prompting and started feeling more like governed engineering collaboration.

## The Working Mode Changed

I code this way personally now.

That is testimony, not a universal claim. But it is a real change in practice.

I now rarely run into obvious AI code errors of the old kind. The recurring problems are usually no longer "the agent broke something because it guessed wildly." They are design problems: unresolved ownership, unclear requirements, competing invariants, architectural tensions that genuinely need a decision.

That is a much better class of problem to have.

It means the friction has moved. Instead of spending energy cleaning up regressions after plausible-but-wrong edits, I spend more energy answering harder questions earlier.

## The Constitution Overrides the Tool

Another thing became clear in practice: the architecture overrides the default interaction modes of the coding tool.

Tools may offer a "plan" mode and an "accept edits on" mode as if these are distinct phases or user toggles. Under a constitutional architecture, that distinction weakens. The model is effectively always in plan mode, because the repository keeps forcing planning questions back into the loop before significant action proceeds.

The constitution does not let the agent glide from intent to edits without passing through orientation, scope, and boundary checks. And it creates hard stops around the moments that matter most institutionally: commits, merges, pushes, destructive operations, and other actions that affect shared state or lock in decisions.

In other words, the harness is not just giving the model context. It is governing when forward motion is allowed and when the Architect has to answer for what is about to happen.

The reviewer pattern sharpened this even further. When Codex produced a serious critique of Claude Opus's code, I often had to arbitrate between two highly specific technical readings of the same change. That routinely surfaced nuances I would not have thought to ask about on my own. In that sense, the review loop was not just checking the code. It was forcing me to stay current enough with the codebase to make better judgments than I would have made earlier.

## From Private Rescue to Public Pattern

The mathematics dojo itself is on a slow rollout. I use it constantly, but the commercial version depends on a slower process of manually writing original questions.

Meanwhile, I kept thinking about the architecture that came out of the refactor.

I published an MIT-licensed repository for the larger Memex pattern and another for its smaller cousin, Gator. The larger interest so far has mostly shown up as cloning and quiet observation rather than active contact from a research community.

That seems normal.

The more important point is that neither Memex nor Gator came from abstract theorizing alone. They came from a practical need: recovering architectural control in a codebase that was becoming productive faster than it was remaining comprehensible.

Once I saw that, it was hard not to wonder where the pattern might go.

Today the "concierge" role in Gator is modest: it helps the primary agent answer recurring Architect questions naturally from the knowledge layer. But the deeper possibility seems larger than that. A more evolved system in this family would not just answer questions. It would surface the hard, architecturally significant questions that the human operator has not resolved yet, and refuse to let them disappear into output generation.

That starts to look less like a chat assistant and more like a new kind of expert system: one that does not merely contain knowledge, but knows when knowledge runs out and judgment must begin.

## Why This Matters

This origin matters because it shapes what these systems are trying to do.

Gator is not primarily an attempt to create better prompts.
It is not primarily an attempt to automate software development more aggressively.

It is an attempt to answer a narrower but more urgent question:

How do you keep repo comprehension, architectural intent, and human judgment synchronized with AI-assisted code generation once generation becomes cheap enough to outrun ordinary review habits?

That is the question from which navigation coding emerged.
