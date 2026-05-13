---
name: obsidian-vault
description: Search, create, and manage notes in an Obsidian vault with wikilinks, backlinks, and index notes. Use when user wants to find, create, or organize notes in Obsidian, or when a vault path needs to be discovered and updated.
---

# Obsidian Vault

## Find the vault

Determine the vault path in this order:

1. A path the user explicitly provided
2. The current working tree or one of its parents if it contains `.obsidian/`
3. `OBSIDIAN_VAULT` or `OBSIDIAN_VAULT_PATH`
4. Common user locations such as `~/Obsidian`, `~/Documents/Obsidian`, or synced folders if they exist

If no vault is discoverable, ask once for the vault path before proceeding.

## Respect the vault's conventions

- If the vault already has a naming convention, follow it
- If there is no obvious convention, use Title Case for note names
- Prefer flat organization with wikilinks unless the vault already uses folders heavily
- Reuse existing index notes before creating new ones

## Search workflows

Use `rg` where possible:

```bash
# Search filenames
rg --files "<vault-path>" | rg -i "keyword"

# Search note contents
rg -l "keyword" "<vault-path>"
```

To find backlinks to a note:

```bash
rg -l "\[\[Note Title\]\]" "<vault-path>"
```

To find index notes:

```bash
rg --files "<vault-path>" | rg "Index\.md$"
```

## Create or update notes

When creating a note:

1. Choose a filename that matches the vault's style
2. Write concise content focused on one topic
3. Add `[[wikilinks]]` to related notes at the end
4. Update an existing index note if one already aggregates the topic

When reorganizing:

- Prefer linking over moving files
- Avoid breaking wikilinks without updating inbound references
- Preserve frontmatter and callouts if the vault already uses them
