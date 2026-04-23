# Forms

## Trigger
需要处理与Word 文档处理相关的任务时

## Output Format
结构化结果

## Standard Steps
1. python scripts/office/unpack.py document.docx unpacked/
2. Extracts XML, pretty-prints, merges adjacent runs, and converts smart quotes to XML entities (`&#x201C;` etc.) so they survive editing. Use `--merge-runs false` to skip run merging.
3. Edit files in `unpacked/word/`. See XML Reference below for patterns.
4. Use "Claude" as the author** for tracked changes and comments, unless the user explicitly requests use of a different name.
