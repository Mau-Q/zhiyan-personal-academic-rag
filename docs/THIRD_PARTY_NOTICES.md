# 第三方代码声明

`backend/ingestion/parser.py`、`backend/ingestion/splitter.py` 和相应合成 PDF 测试代码，基于 Zhiyan Paper Reading Agent 中的解析、切分及测试实现进行裁剪和适配：

- Source: <https://github.com/Mau-Q/zhiyan-paper-reading-agent>
- License: MIT
- Copyright (c) 2026 Zhiyan Paper Reading Agent contributors

MIT License

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## 可选 Reranker 运行依赖

固定 Reranker Gate 通过可选依赖使用以下未修改的第三方项目与模型；
仓库不提交模型权重：

- Sentence Transformers: <https://github.com/huggingface/sentence-transformers>,
  Apache License 2.0；
- `BAAI/bge-reranker-v2-m3`:
  <https://huggingface.co/BAAI/bge-reranker-v2-m3>,
  Apache License 2.0。
