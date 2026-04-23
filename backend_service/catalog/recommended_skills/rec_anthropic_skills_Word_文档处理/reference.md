# Reference

## Summary
触发：需要处理与Word 文档处理相关的任务时 | 目标：A .docx file is a ZIP archive containing XML files. | 步骤：python scripts/office/unpack.py document.docx unpacked/；Extracts XML, pretty-prints, merges adjacent runs, and converts smart quotes to XML entities (`&#x201C;` etc.) so they survive editing. Use `--merge-runs false` to skip run merging.；Edit files in `unpacked/word/`. See XML Reference below for patterns. | 产出：结构化结果

## Sources
- recommended_catalog
