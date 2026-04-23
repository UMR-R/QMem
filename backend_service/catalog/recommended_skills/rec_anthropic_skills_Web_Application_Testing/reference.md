# Reference

## Summary
触发：需要处理与Web Application Testing相关的任务时 | 目标：To test local web applications, write native Python Playwrig | 步骤：`scripts/with_server.py` - Manages server lifecycle (supports multiple servers)；**Use bundled scripts as black boxes** - To accomplish a task, consider whether one of the scripts available in `scripts/` can help. These scripts handle common, complex workflows reliably without cluttering the context window. Use `--help` to see usage, then invoke directly.；Use `sync_playwright()` for synchronous scripts | 产出：操作步骤 / 调试建议

## Sources
- recommended_catalog
