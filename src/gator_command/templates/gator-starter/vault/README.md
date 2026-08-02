# Vault

Private, sensitive, or large files that must not be committed to Git. The vault is gitignored by default — anything placed here stays on your local machine.

## What goes in the vault

- API keys, credentials, tokens
- PDFs, datasets, large files
- Private notes not meant for version control
- Sensitive client or business material

## How to use it

Simply save files here. They will not appear in `git status` or be committed.

Ask your AI coding agent:

> "Save this API key to the vault."

> "Put this PDF in `.gator/vault/` so I can reference it."

The agent can read vault files during a session but they will never be committed or shared via Git.

## Security note

The vault relies on `.gitignore` rules. It is not encrypted. If your machine is compromised, vault contents are accessible. For credentials that require stronger protection, use a dedicated secrets manager.
