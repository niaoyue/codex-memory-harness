# Skills

本目录用于放置与 Codex 外脑系统配套的技能文件。

当前包含随包安装的 upstream curated skills：

- `bundled-skills.json`：来源、固定 commit 和默认安装清单。
- `openai-curated/`：从 `https://github.com/openai/skills` 的 `skills/.curated` 固定提取的技能文件。
- `local/`：本项目自带的 install-propagated workflow skills。

安装器默认把清单中的技能安装到 `~/.agents/skills/<skill-name>`。如果 Codex 已提供同名 `.system` 技能，则跳过用户目录副本；如果目标目录已存在且内容不同，会先备份到 `.codex-memory-backups/` 再刷新；如果旧版 `~/.codex/skills` 中还有同名技能副本，会把旧副本备份移出发现路径。可用 `--skip-skills` 跳过该步骤。
