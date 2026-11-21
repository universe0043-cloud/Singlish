# Singlish：英文歌曲跟读学习系统

深度学习课程项目，面向希望借英文歌练习自然口语的学习者。上传英文 MP3 后，本地 faster-whisper 识别歌词和时间；有可核对的内嵌或本地参考歌词时进行校正与对齐；DeepSeek 提出发音候选；Python 校验位置、类别和证据，通用规则补充明确的候选，再生成和转换 IPA，网页提供逐句试听与词下中文提示。

这是保留当前真实网页的最小课程提交版。没有附带私人歌曲、密钥、模型、运行缓存、报告占位稿或历史材料全集。原始档案仍在原运行项目中。本目录不含 Git 仓库。

## 环境与安装

已验证 **Windows 11 x64、Python 3.13.2**。前端为原生 HTML/CSS/JavaScript，后端为 Python 标准库 HTTP 服务，无需 Node 或前端构建。Linux/macOS 未实测。

在本目录打开 PowerShell：

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
```

只保留一份 `requirements.txt`：原已验证 Windows 环境的 38 个发行包固定版本，包括传递依赖。它是该环境复现清单，其他系统需要验证 wheel 兼容性；未声称跨平台可直接安装。PyAV wheel 提供解码，已验证环境无需另装 FFmpeg 命令行。

本次最小版核对复用了原项目的现有环境，依赖检查通过；没有另装环境、重新下载权重或调用付费模型。

## 本地模型准备

```powershell
.\.venv\Scripts\python.exe -B -m tools.download_model
```

下载 `Systran/faster-whisper-small.en`，固定修订版 `d1d751a5f8271d482d14ca55d9e2deeebbae577f`，保存到 `.singlish-cache/models/`。运行使用 CPU int8，最多 6 个 CPU 线程，不要求 GPU。首次准备需要网络和磁盘空间，不是收费 API。模型权重不在提交目录。

已有完整模型缓存时，可私下复制到相同的相对目录并检查，禁止把权重上传仓库：

```powershell
.\.venv\Scripts\python.exe -B -m tools.download_model --local-files-only
```

未测最低内存要求和完整冷下载耗时，不填写估计值。

## 密钥配置

仅当 `.env` 不存在时复制，避免覆盖个人配置：

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

在 `.env` 中替换占位值：`SINGLISH_API_KEY`、`DEEPSEEK_BASE_URL`、`DEEPSEEK_MODEL`；可选 `SINGLISH_DEBUG_SPANS=0`。服务按项目位置加载配置，系统环境变量优先。Key 只在服务端读取，不填入网页或源代码。真实分析向所配置平台发送歌词文本，可能收费；本地转写不向语言模型发送录音。当前网页基于 pilot-02 的定位协议扩展 `pronunciation-v0.3-pilot-02-locations-01`，与下述两个历史实验提示词分别保留。

## 启动与使用

```powershell
.\.venv\Scripts\python.exe -B -X utf8 -m web.server --port 8767
```

访问 <http://127.0.0.1:8767/>，终端保持运行，`Ctrl+C` 退出；端口占用时更改 `--port`。默认仅监听本机，不是公网部署服务。

1. 点击“上传歌曲”，选择不超过 **30 MB** 的英文 MP3，等待歌词与分析进度。没有可靠参考时进入本地转写。
2. 在“歌词与跟读”中逐句试听、调倍速或单句循环。点击发音高亮或其下的“常规读法／口语示范”，就近查看中文提示；重叠标注均保留。
3. 行内“改词”可纠错，保留原时间；仅发音分析失败时歌词与试听仍保留，并提供重试。实际重试会请求所配置平台。
4. 点击 Singlish 字标返回上传首页，暂停播放和循环；数据缓存不删除，可更换歌曲。

五类：弱读、连读、省音、变音、缩读。连读等是有条件的教学候选，`actual_pronunciation=uncertain`，不能断言歌手的实际读法。词典式宽式英式 IPA 为展示基础，必要的美式变体仍说明条件，原 IPA 保留。

### 无密钥离线演示

```powershell
.\.venv\Scripts\python.exe -B -X utf8 -m web.server --demo --port 8767
```

在“使用指南”展开“也可以直接输入歌词”，粘贴 `I'm gonna buy a better seat.`。另可输入 `We can walk in.`、`Meet me next Monday.`、`Go slow.`。这是现有演示入口读取四句已保存响应，不加载 `.env`、不调用 API；不是任意歌曲的离线模型。`Go slow.` 的模型原始响应为空，页面通用规则仍可能另作补充。

## 主要实验复现（完全离线）

```powershell
.\.venv\Scripts\python.exe -B -X utf8 -m tools.replay_test40
```

工具禁止网络连接，不加载 `.env`，不修改输入、参考或已保存响应。核对 **40 题、55 条冻结参考、3 道空答案、两版共 80 条响应**，按“题号 + start/end + category”严格匹配，0-based、右端不含，逐条验证原文切片。完整题目校验失败计无可用预测；合法空数组计校验通过。两版使用相同参考、校验器和算法。没有把网页通用规则补充计入模型成绩。

`experiments/main_results.csv` 是唯一主要结果表，含全体、日常口语和歌词三组共 12 行。命令核对每一行的 TP/FP/FN、Precision/Recall/F1、通过数和空响应数；不写回表格。可用 `--output 新路径.json` 另存详情，拒绝覆盖旧文件。

| 阶段 | 提示词 | 通过数 | TP | FP | FN | F1 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 原始评分 | pilot-02 | 39/40 | 36 | 18 | 19 | 0.660550 |
| 原始评分 | pilot-03 | 39/40 | 35 | 20 | 20 | 0.636364 |
| 定位修复重放 | pilot-02 | 40/40 | 37 | 18 | 18 | 0.672727 |
| 定位修复重放 | pilot-03 | 40/40 | 37 | 20 | 18 | 0.660714 |

阶段边界：

- **原始评分**：从同一份响应档案内当时保存的 `validated_output/status/error` 重新计算评分；没有恢复并重新运行历史校验器。档案的 `raw_response` 原文仍保留，原始评分未改写。
- **定位修复重放**：将相同 `raw_response` 重新送入现行校验器；支持 Lemme，并在无原样匹配时才允许按完整词边界消除大小写差异；重复片段仍须可靠消歧。不是再次模型实验。

响应档案记录模型 `deepseek-flash`、请求配置、原始正文与当时输出；未记录权重版本，不能推断其固定权重。两个提示词文本在 `experiments/prompts/`，字节哈希核对档案 manifest；运行期仍由 `src/pronunciation.py` 与 `data/pronunciation_pilot_v0.3/v0.4.jsonl` 生成相同提示词。这两份数据是实际依赖，不能当无关试点删除。v0.4 指南保留在 `data/`。

55 条参考仍 **pending_human_review**，以上均为初评，不是人工终评。后续 56 条 AI 辅助修订候选待人工终审，本轮没有用于评分，未放入最小目录。AI 工具参与代码、数据草稿及复核建议整理，DeepSeek 生成实验预测；参考与教学提示仍需人工核实，不把 AI 建议称为人工确认。

## 目录与来源

```text
src/           当前后端分析、校验、定位与提示词源码
web/           当前页面、播放交互、任务、转写、对齐及 IPA 处理
data/          必要 IPA 词典与许可、两份提示词运行数据、v0.4 指南和句子入口样例
experiments/   两个提示词、40 题、55 条冻结参考、80 条响应、主结果表；四句运行演示响应
tools/         模型准备、主要实验离线复现
licenses/      不同的第三方许可原文（逐字相同的副本合并保留，映射见来源说明）
```

第三方、数据和素材来源统一见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。它包含依赖版本与许可文件映射，必要许可原文继续保留。没有占位报告或截图合集，README 不依赖截图。项目自有代码尚未指定统一开源许可证；设计素材来源授权与歌曲研究材料的引用依据仍需作者补全。

## 主要限制与本次检查边界

- 本次已用现有 Python 环境核对启动、静态资源、API 配置、四句离线任务、IPA 输出和主要实验表；未新做完整 MP3 转写、真实 DeepSeek 或浏览器人工点击验收。未测的耗时、内存、识别准确率和并发容量不提供估算。
- 唱腔、伴奏、合唱、重复句会造成错词、漏句和时间偏差；无参考时更需人工校对。模型与规则均可能误标漏标。
- 任务可查进度，但刷新不自动恢复当前任务和浏览器音频；进程重启丢失内存任务。磁盘复用不等于完整断点恢复。
- 无账号、权限或用户隔离；同一音频共享本机纠错缓存。两条工作线程、有队列上限和阶段锁，没有多人容量验证、生产队列或跨进程同步。
- 标准库本机服务，无公网 TLS、正式生产部署或 Docker，不能直接开放为多用户网站。
- `.singlish-cache/` 含模型、歌词、结果与运行日志；音频本体不持久保存。真实 `.env`、音频、权重、缓存及虚拟环境均不在提交目录，网页上传不会自动应用 `.gitignore`，不要自行添加这些文件。
