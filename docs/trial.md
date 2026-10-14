# 有限试读

本轮实现使用 Python 标准库，无额外 Python 包。输出 JSON、Markdown 和离线 HTML；打开成品不会调用模型。

## 离线检查

```sh
python -m unittest discover -s tests -v
python scripts/trial.py --tasks config/trial-sources.json --output data/preview
python scripts/render_trial.py data/preview
```

默认仅生成提示预览，没有回答。种子内的短摘录用于结构检查；真实生成应先用 `scripts/prepare_sources.py` 获取正文。遇到站点拦截时删除依赖题，不以模型知识冒充来源。可传入实际读取并记录时间、URL 的私有来源缓存，具体参数见脚本 `--help`。

## 订阅与试跑

`scripts/codex_adapter.py preflight` 仅读取当前 Codex 登录类型、额度窗口和模型目录。程序通过已有 `CODEX_HOME` 使用订阅；不自行读取认证文件，不使用 API key 回退。模型与推理强度必须出现在实际目录中。

一般 live 模式需要可信提供方限额核验适配器；当前没有实现可用的独立应用硬限额查询，不要用自填 JSON 假装核验通过。

经实例所有者明确接受共享额度风险后，可使用 `--observed-trial-risk-accepted` 做有限试验：最长 1200 秒、最多 8 次调用（含重试）、串行逐题前后核对额度。额度未知、窗口变化、用量增幅达到阈值或授权失效时停止。**这些是保守观测措施，不是提供方硬计费上限；超时不能撤销已发生的消耗。** 不应据此直接启用长期无人值守服务。

模型命令和额度命令使用私有 JSON argv 文件，不拼接 shell。示例：

```json
["python3", "scripts/codex_adapter.py", "generate", "--model", "实际可用模型", "--reasoning-effort", "low"]
```

额度命令：

```json
["python3", "scripts/codex_adapter.py", "usage"]
```

完整参数参见 `scripts/trial.py --help`。输出目录必须每次独立；同一已完成目录不会重复生成。中断时保留状态并要求检查，不会无条件重发可能已经计费的请求。

## 内容检查与局限

每个回答含结论、三条简短解释、逐字证据、边界、指标和未知项。引用必须来自输入原文，并绑定对应论断；这只能证明引用存在，不能证明推断必然正确。阅读页明确保留该区别。

源码不携带实例服务器、实际预算、认证或个人阅读数据。公开 PR 不得自动在带有订阅凭据的执行器上运行；私有控制端只能执行已检查的固定提交。
