# Trammel wiki (local)

**Version:** 3.12.1 · **Last updated:** 2026-04-29

This folder holds deeper project documentation for humans and agents. Root-level files stay the canonical quick references; this wiki expands terminology, behavior, and contracts.

**Integration:** Trammel’s contract is **SQLite + API + CLI**; **MCP is optional** (see [spec-project.md](spec-project.md) §1.1). Sub-agents often do not use MCP; align them via the store and exported plans, not the protocol.

## Pages

| Page | Description |
|------|-------------|
| [spec-project.md](spec-project.md) | Architecture, constraints, APIs, SQLite schema, MCP tools, verification flow |
| [glossary.md](glossary.md) | Named concepts (beam, recipe, strategy, constraint, harness, ...) |

## Root docs (repo)

| Path | Role |
|------|------|
| [../README.md](../README.md) | Quickstart, CLI, MCP setup, architecture, version |
| [../COMPLETE_PROJECT_DOCUMENTATION.md](../COMPLETE_PROJECT_DOCUMENTATION.md) | File inventory and data flow |
| [../LLM_Development.md](../LLM_Development.md) | Chronological change log |

## Stele

Project sources and these wiki pages are indexed in **Stele** (`user-stele-context`) for semantic search and context retrieval in the IDE.
