# Ask

在服务器提前生成可连续阅读的中文知识读本。输出纯文本，不开发网页。

每个主题有固定目录和前置关系；章节承接已完成内容，围绕相邻概念、机制、证据、反例与应用逐层展开。首个主题为“创新药：从临床证据到企业现金流”，目录见 [knowledge-plan.json](config/knowledge-plan.json)。

## 运行

使用 Python 标准库与已登录的 Codex。先准备包含实际原文的私有来源包，再预演：

```sh
python3 scripts/knowledge.py --plan config/knowledge-plan.json --sources .local/knowledge-sources.json --output data/knowledge
```

预演不调用模型。明确启用 `--run` 才生成；每次最多八次调用、二十分钟，模型必须在实际可用目录中。逐章观察额度，异常或增幅达到阈值就停；这种观测不是提供方硬额度限制。实例限额与授权独立保存，不使用 API key 回退。

## 查看结果

- `index.txt`：目录、顺序和前置章节。
- `knowledge.txt`：连贯合订正文，已完成的部分立即可读。
- `status.txt`：当前章节、完成数量、最近更新时间和停止原因。
- 各章 `.txt`：便于单独阅读；已完成章节不会重复生成。

这是有限试运行入口，长期调度尚未启用。先前卡片实验未达到系统阅读要求，已停止；旧代码仅供复现记录。

## 开源方案参考

[STORM](https://github.com/stanford-oval/storm) 支持多视角连续追问、组织大纲、按章节写作和文本输出；[GPT Researcher](https://github.com/assafelovic/gpt-researcher) 支持无界面研究报告。两者默认模型接入均需另配 API，不能据此假定会使用现有订阅。

当前只借鉴 STORM 的提问与组织方法，增加前置依赖；没有安装、运行或复制 STORM 的代码。为复用已验证的订阅登录，本轮使用单个轻量章节脚本。实际内容质量仍需核查，不能把模型完成事件当作事实已正确。

实例信息与原文缓存放在 `.local/`，阅读内容放在私有数据目录，不提交到公开仓库。实施跟踪：[任务 #1](https://github.com/maxwelles666/ask/issues/1)。
