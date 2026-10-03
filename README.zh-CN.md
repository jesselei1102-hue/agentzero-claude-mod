# AgentZero for Claude Code

[English](./README.md) | **简体中文**

MIT · 一个 Claude Code 插件

装上这个插件，你就在 Claude Code 里拥有完整的 [AgentZero](https://github.com/jesselei1102-hue/agentzero)。安装走插件市场。

插件里带着一份固定版本的 AgentZero，运行的就是同一套代码。没有重写，所以不会和原版分叉。

插件还多做两件事。这两件事只有跑在 Claude Code 引擎里的插件才做得到。

1. **它替你加载 hot set。** 第一条消息、`/compact` 或 `/clear` 之后、隔了六小时之后，插件会运行 `./a0 memory hot-set`。结果会连同你的消息一起交给模型。agent 不用再记着自己去跑。
2. **它核对“你说过的话”。** agent 运行 `memory remember --said "…"` 时，插件会在你本次会话输入的内容里找这些话。找到了，命令照常运行。找不到，这条 Fact 会记成**提议**，并提醒 agent 去问你。

## 安装

在 Claude Code 里运行：

```text
/plugin marketplace add jesselei1102-hue/agentzero-claude-mod
/plugin install agentzero@agentzero
```

安装范围请选最窄的（project 或 local）。这样插件只在你要用的项目里生效。

## 给项目装上 AgentZero

打开要工作的文件夹，运行：

```text
/agentzero init
```

这个文件夹就成了 Claude Code 用的 AgentZero 工作区。文件、`CLAUDE.md`、Trace hooks 和 `./a0` 启动器，和 AgentZero 自带的 `adapter init --harness claude` 做出来的完全一样。然后**开一个新会话**。`CLAUDE.md` 和 hooks 要在会话开始时才会加载。

下面这些文件夹，`init` 会拒绝：你的主目录、文件系统根目录、已经是工作区的文件夹、工作区里面的文件夹。

其他命令：

| 命令 | 作用 |
|---|---|
| `/agentzero upgrade` | 把工作区升到插件自带的 AgentZero 版本。你改过的框架文件不会被覆盖。被拦下时，它会如实显示原因。 |
| `/agentzero status` | 显示工作区能不能运行，以及插件和 AgentZero 的版本。 |

## 插件多做了什么，以及它的限制

- **只支持 Claude Code。** Codex 和 Cursor 仍用 AgentZero 自己的规则和提醒。插件不碰它们。
- **核对只能证明那些话是你说的，不能证明是你说的全部。** 引用被截短，仍然是你输入内容的一部分，所以会通过。
- **有些 `remember` 的写法不会被核对。** 插件只认一种形式：可选的 `cd <目录> &&`，然后是 `./a0 memory remember …`（或 `python -m memory remember …`），参数是普通的带引号文字。用了变量、管道或 `--workspace` 的命令会原样运行。你会看到“这条 remember 里的话没有核对”。
- **提示会出现在两个地方。** 桌面 app 没有状态栏。所以插件的每条提示也会弹出 toast。
- 如果 hot set 加载失败（`./a0` 出错、超过 10 秒、没有输出），插件会说明原因，并且什么也不加。AgentZero 自己的六小时提醒仍然作为后备。

## 环境要求

- 支持 function hooks 的 Claude Code（在 2.1.280 和 2.1.286 上试过）。
- Python 3.11 或更高，并装有 PyYAML：`python3 -m pip install pyyaml`。插件会找 `python3`、`python` 和常见的安装目录。工作区里的 `./a0` 会自己找 Python。
- macOS 或 Linux。**Windows 还没有验证。**

## 版本

插件有自己的版本号。`kernel/SOURCE.json` 记录了 AgentZero 的提交、版本，以及固定副本里每个文件的 SHA-256。有一个测试会用它核对这份副本。详见 [CHANGELOG.md](./CHANGELOG.md) 和 [DECISIONS.md](./DECISIONS.md)。
