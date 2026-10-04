# agentzero-claude-mod

[English](./README.md) | **简体中文**

把 [AgentZero](https://github.com/jesselei1102-hue/agentzero) 做成 Claude Code 插件。从插件市场装上，你就有完整的 AgentZero。另外多两件事，只有跑在引擎里才做得到：

- 它**替你加载 hot set**，agent 不用自己记着去跑；
- 记录“你说过的话”之前，它**核对这句引用是不是你说的**。

插件里带着一份固定版本、有哈希校验的 AgentZero，运行的是同一套 Python 代码。没有重写，所以不会和原版分叉。插件自己的 TypeScript 大约 600 行。

## 安装

```text
/plugin marketplace add jesselei1102-hue/agentzero-claude-mod
/plugin install agentzero@agentzero
```

安装范围选最窄的（project 或 local），这样插件只在你要用的地方生效。然后在项目文件夹里运行：

```text
/agentzero init
```

在这个文件夹里开一个**新会话**。`CLAUDE.md` 和 hooks 要到会话开始时才加载。得到的工作区，和 AgentZero 自带的 `adapter init --harness claude` 做出来的一样。

需要 Python 3.11 或更高，并装有 PyYAML（`python3 -m pip install pyyaml`）。支持 macOS 和 Linux。

## 它做什么

### 1. hot set 跟着你的消息一起到

AgentZero 的规则 3：每个会话加载一次 hot set，压缩之后再加载一次。以前要 agent 自己运行命令，它有时没做（隔了 19 小时那次，见 AgentZero 的 SETTLED #89）。

现在插件会运行 `./a0 memory hot-set --hints "<你消息的前 200 个字符>"`，把输出附在你的消息上。模型读得到，你看不到。触发时机：

- 一个会话里你的第一条消息；
- `/compact` 或 `/clear` 之后的第一条消息；
- 隔了六小时之后的第一条消息。

附上的文字会告诉 agent 不要再自己跑 `hot-set`。耗时约 100 毫秒。如果 `./a0` 出错、超过 10 秒或没有输出，插件什么也不附，并说明原因：`AgentZero: hot set not loaded (exit 1)`。

### 2. 引用必须是你说的

`memory remember --said "<原话>"` 把一条 Fact 记成“你说的”。命令看不到对话，分不出这是你的原话，还是 agent 编的。

插件分得出。agent 运行 `remember` 时，插件会在你本次会话输入的内容里，找 `--said` 的整段文字。空白差异会被忽略，包括全角空格和不换行空格。

```text
你：    我们这个项目所有尺寸都用毫米。
agent： ./a0 memory remember "…mm…" --said "我们这个项目所有尺寸都用毫米。"
插件：  找到了 → 原样运行 → remembered: …

agent： ./a0 memory remember "…mm…" --said "(转述) 操作者确认用毫米"
插件：  没找到 → 改为运行 `./a0 memory propose fact "…mm…"`，并告诉 agent：
        “已记成提议，请去问操作者。”
```

提议要等你点头（`./a0 memory review`）。对不上的那句话不会被保存。

### 3. `/agentzero`

| 命令 | 作用 |
|---|---|
| `init` | 把当前文件夹变成 Claude Code 用的 AgentZero 工作区。会拒绝你的主目录、`/`、已有的工作区，以及工作区里面的文件夹。 |
| `upgrade` | 把工作区升到插件自带的 AgentZero 版本。不会覆盖你改过的框架文件，被拦下时会显示原因。 |
| `status` | 工作区能不能运行，以及插件和 AgentZero 的版本。 |

## 限制

- **只支持 Claude Code。** Codex 和 Cursor 仍用 AgentZero 自己的规则和提醒。
- **截短的引用能通过。** 核对只能证明这些话是你说的，不能证明是你说的全部。截短的引用仍是你输入内容的一部分。
- **只认一种 `remember` 写法：** 可选的 `cd <目录> &&`，然后是 `./a0 memory remember …`（或 `python -m memory remember …`），参数是普通带引号的文字，只支持 `--said --fact-key --scope --tag --source-run` 这几个选项。其他写法（变量、管道、`--workspace`）会原样运行，你会看到“这条 remember 里的话没有核对”。
- **桌面 app 没有状态栏**，所以插件的每条提示也会弹 toast。
- **还没验证：** Windows；终端和 VS Code 里的消息来源类型（核对接受 `composer`、`bridge`、`sdk`；桌面 app 发的是 `composer`）；在从没用过 AgentZero 的机器上首次安装。
- 它基于 Claude Code 的 function hooks API。这个 API 还在抢先体验阶段，版本之间会变。已在终端的 2.1.280 和桌面 app 的 2.1.286 上试过。

## 怎么搭的

```text
.claude-plugin/marketplace.json     一个插件
plugins/agentzero/
  hooks/                            两个功能和 /agentzero，连同测试
  kernel/                           固定版本的 AgentZero；SOURCE.json 记录提交和文件哈希
scripts/sync_kernel.py              把 AgentZero 的某个提交复制进 kernel/
tests/                              pytest：同步脚本，以及 kernel/ 对照它的清单
docs/                               设计说明、计划，以及验证记录（verify.md）
```

运行测试：

```bash
claude plugin test plugins/agentzero      # hooks
python3 -m pytest                          # 同步脚本和 kernel 清单
```

跟进 AgentZero 的新版本：`python3 scripts/sync_kernel.py <AgentZero 检出目录> --ref <标签> --denylist <文件>`，然后发布新的插件版本。

详见 [CHANGELOG.md](./CHANGELOG.md) 和 [DECISIONS.md](./DECISIONS.md)。

## 许可证

MIT。`kernel/LICENSE` 是 AgentZero 自己的。
