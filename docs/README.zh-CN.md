# latex2md：中文使用指南

独立仓库 `laughtale-lab/latex2md`，适配 Diabat 2.0 Manual 既有的 LaTeX
源文件，不修改 LaTeX 正文和排版。代码使用 MIT 许可证；手册内容及图片继续遵守原手册许可证。

## 安装

需要 Python 3.11 或更高版本，不需要第三方 Python 运行依赖。

```bash
python -m pip install .
latex2md build --source /path/to/diabat-manual --output /tmp/diabat-book
```

`--output` 应为空目录或者尚不存在。生成 `book.toml`、`src/SUMMARY.md`、
逐章 Markdown、关键词链接、参考文献、数学公式及代码配色脚本。
原始 `.inp` / `.gjf` 按字节复制至 `src/downloads/examples/`，
排版专用 `.lst` 则只转成网页代码块。部分计算示例仍需要外部计算数据。

预览（第二阶段仅验证转换，不正式发布网页）：

```bash
mdbook build /tmp/diabat-book
mdbook serve /tmp/diabat-book --open
```

当前建议锁定 mdBook 0.4.52；更换 mdBook 或转换器版本应分别回归测试。

## 自动测试与发布原则

```bash
python -m unittest discover -s tests -v
latex2md-verify \
  --report /tmp/diabat-book/conversion-report.json \
  --baseline docs/diabat-2.0-baseline.json
```

基线是这次上传手册的快照，而不是后续章节不能变化的限制。
CI 会检出公开的 `diabat-manual` 当前 `main` 并测试转换、HTML 预览。
正式接入第一仓库前，仍需该仓库指定转换器已验证的**提交 SHA**。
全部步骤完成且成功后才与对应的 PDF 一起部署。

若某个宏、标签、资源或者文献失效，程序会以非零返回值结束，
不会在错误情况下生成并替换正式发布目录。具体设计和接入方案分别
见 `docs/DESIGN.md` 和 `docs/INTEGRATION.md`。
