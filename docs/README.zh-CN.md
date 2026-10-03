# latex2md：中文使用指南

`latex2md` 独立于 `diabat-manual`，适配现有 Diabat Manual LaTeX 源码，
不修改 Manual 正文、宏定义和印刷排版。LaTeX 始终是唯一正文源文件。

## 安装与转换

需要 Python 3.11 或更高版本：

```bash
python -m pip install .
latex2md build --source /path/to/diabat-manual --output /tmp/diabat-book
```

标题后的 LaTeX `\label` 会结构化绑定到标题，并生成 mdBook 原生 heading
attribute，例如：

```markdown
### 2.2.1 Standard output and error output { #sec-stdout }
```

Script、Example、关键词、独立 label 和参考文献使用显式、唯一的 HTML
目标。`conversion-report.json` 的 `targets` 字段记录最终网页必须出现的
全部目标。

## 固定 mdBook 0.4.52 后的最终审计

```bash
mdbook build /tmp/diabat-book
latex2md-audit-html \
  --report /tmp/diabat-book/conversion-report.json \
  --html /tmp/diabat-book/book \
  --allow-missing diabat.pdf
```

`--allow-missing diabat.pdf` **只用于转换器独立 CI**，因为此时 PDF 尚未
由 Manual 仓库一起放入网站目录。正式 `diabat-manual` 发布时必须先把
PDF 和 HTML 放入同一 staging 目录，再运行不带该例外的最终审计。

审计会检查每个登记目标在真实 mdBook HTML 中恰好出现一次，标题目标
必须位于正确的 h1/h2/h3 等元素，Script/Example 必须保留
`listing-caption` 语义；所有本地页面、fragment 和资源都必须真实存在。
任何失败都会返回非零状态，禁止继续发布。

## 发布原则

CI 固定使用 mdBook 0.4.52，并先跑最小真实渲染 fixture，再跑完整当前
Manual。只有两个真实 mdBook HTML 审计都通过并完成人工网页检查后，
才可以给转换器创建新 tag。正式 Manual 集成始终固定转换器完整 commit
SHA，不跟随 `latex2md/main`，也不使用 submodule。
