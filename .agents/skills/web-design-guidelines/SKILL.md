---
name: web-design-guidelines
description: Review UI code for Web Interface Guidelines compliance. Use when asked to "review my UI", "check accessibility", "audit design", "review UX", or "check my site against best practices".
metadata:
  author: vercel
  version: "1.0.0"
  argument-hint: <file-or-pattern>
---

# Web Interface Guidelines

Review files for compliance with the Web Interface Guidelines.

## Rules

Read `rules.md` next to this file. It holds the complete rule set and the output format.

## How It Works

1. Read `rules.md`
2. Read the specified files (or ask which files to review)
3. Check against every rule
4. Report findings in the terse `file:line` format `rules.md` specifies

## Why the rules are vendored

Upstream this skill fetched its rules from the network on every run, and said outright that the
fetched content carries its instructions. That makes the skill's behaviour a live remote channel:
what it tells the agent to do can change with no change in this repository, and nothing here was
reviewed. The rules are therefore kept as a file, reviewed like any other file in the tree.

Source: https://github.com/vercel-labs/web-interface-guidelines — `command.md`
Vendored 2026-09-09, sha256 5a775e6411f790f518dbc9c1fa7c50a89e6873502d9a3530a6eb223a590bcfe8

To take a newer version, fetch that file over `rules.md`, read the diff, and update the hash above.
