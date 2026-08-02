# Policies

Organizational standards and coding conventions that apply across this project. Policies are rules that the AI agent should follow consistently — they shape how code is written, not what code does.

## When to create a policy

- You have a coding convention the AI agent keeps forgetting between sessions
- A standard needs to be explicit (naming conventions, error handling patterns, testing requirements)
- You want consistent behavior across multiple AI agents working on the same project

## How to create one

Ask your AI coding agent:

> "Create a policy for [convention]. Save it to `.gator/policies/`."

> "We always [do X] in this project. Write that up as a policy."

## What makes a good policy

- Short and specific: one convention per policy
- Actionable: the agent can follow it without interpretation
- Scoped: says when the policy applies (all code? only tests? only Python files?)

## What policies are not

Policies are not code documentation (use charters), not design rationale (use artifacts), and not procedures (step-by-step workflows). They are standing rules.
