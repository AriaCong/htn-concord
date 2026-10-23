# 项目介绍幻灯片 · 源码

上一级目录里的两个 `.pptx`（中文 `RuleBench_Overview_zh.pptx`、英文 `RuleBench_Overview.pptx`）由脚本生成，不要手改。改文字后重新生成：

```bash
uv run --no-project --with python-pptx python build_deck.py ..
```

- `content_rb.py`：全部文字，中英两版，一次改两份。数字来自先导实验定稿报告、MIMIC 可行性报告和成本估算，出处写在文件开头。
- `build_deck.py`：直接调用 HTN-Concord 的版式函数（`htn-concord-main/docs/slides/src/build.py`、`deck_lib.py`，只读引用、不修改），所以两份幻灯片外观一致。第 14 页（先导结果）另写了一个列宽不同的版本。
- 生成时会打印 `layout check: no overflow`；出现 `OVERFLOW` 说明某段文字可能放不下。这个检查只是估算，最终以 PowerPoint 实际显示为准。
