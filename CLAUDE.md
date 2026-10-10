# CLAUDE.md

Project: the official SarnAI Python package, published to PyPI as `sarnai`.
The brand is always written "SarnAI"; code names (package, modules, functions) are lowercase.

## Prompt rules

- One goal per prompt. Do that goal, then report and stop.
- The user approves every push. Commit locally on a branch; never push without explicit approval.
- No secrets in chat. Never ask for, print, or commit API keys or tokens; read them from the environment.
- Give results in copy-paste format: plain text or commands in fenced code blocks.

## API sources

Learn the public SarnAI APIs only from:

- https://board.sarnai.dev/llms.txt
- https://verify.sarnai.dev/llms.txt

Do not read other repos to infer API behavior, and do not guess endpoints.
