# AGENTS.md

Qwen3-ASR 语音转写定位服务（Python ≥3.12 + FastAPI），uv 管理依赖。

## 命令

- 安装依赖：`uv sync --extra lid`（`funasr` 在可选组 `lid` 中，`lid.enabled = true` 时必需）
- 启动服务：`uv run main.py`（等价 `uv run python -m asr_qwen`；`server.workers > 1` 时以 `asr_qwen.server:app` 运行）
- 下载模型：服务启动（`ModelRegistry.load`）时自动检测并在缺失时从 ModelScope 下载（`asr_qwen/models/download.py`），目录已存在则跳过
- 校验类型/导入：`uv run python -c "import asr_qwen.server"`
- 无测试套件、无 lint 配置；新增时一并在此登记。

## 架构

`asr_qwen/` 分层，依赖方向单向向下：`api`（FastAPI 装配与路由）→ `pipeline`（localize 编排：语种判定 → 转写 → 句段/关键词/标题后处理）→ `models`（ModelRegistry 持有 Qwen3-ASR + 可选 SenseVoice LID）、`audio`（读写/VAD 分块）、`language`（语种码表与多策略判定）、`text`、`config`。运行时上下文挂在 `app.state.context`（AppContext：settings + registry）。

## 注意事项

- **torch 走专用索引**：torch/torchaudio 经 `tool.uv.sources` 固定从 PyTorch cu128 索引安装（PyPI/清华源在 Windows 上只提供 CPU 轮子），其余包走清华默认源；改 torch 版本前确认 cu128 索引上有对应轮子。重依赖（`qwen_asr`、`modelscope`、`funasr`）已入 `pyproject.toml`，但模块内仍一律函数内延迟导入（如 `registry.py`、`audio/io.py`），不要改为顶层导入。
- **音频解码依赖 torchcodec + FFmpeg**：`torchaudio.load/save` 的实际解码走 `torchcodec`（已入依赖），Windows 上还需本机安装 FFmpeg **shared** 版（FFmpeg 4–9 的 DLL，加入 PATH），否则上传 mp3/m4a 等格式在 `audio/io.py` 处报 ImportError。
- **配置零默认值**：`asr-qwen.yml` 所有字段必填，`config/loader.py` 严格校验并抛 `ConfigError`；新增配置需同步改 `settings.py`（frozen dataclass）+ `loader.py` + YAML。
- **配置定位**：显式参数 > `ASR_CONFIG_PATH` 环境变量 > 项目根 → 包目录 → cwd，取第一个存在者；YAML 中相对路径相对该 YAML 所在目录解析。
- **禁止验证**：不要运行任何验证、编译或测试（包括 `uv sync`、`uv run`、导入检查、测试套件）；改动后仅做静态确认，不执行命令。
- 仓库行尾统一 LF（`.gitattributes`）；`.gitignore` 忽略 `.venv/`、`__pycache__/`、`qwen-models/`、`.atomcode/`、`.idea/`，新增本地产物时同步登记。
- 模型权重放 `qwen-models/`（不提交仓库），缺失时服务启动自动从 ModelScope 下载（`modelscope` 包需环境已预装）；未加载完成时 `/asr/localize` 返回 503，`/health` 可查状态。
- 测试页面：`GET /ui`（`asr_qwen/api/testui.py`，内嵌 HTML，无新依赖），随服务一起启动。转写入口两个：`POST /asr/localize` 同步接口；`POST /asr/jobs` 创建后台任务（daemon 线程执行），`GET /asr/jobs/{job_id}` 查询阶段/整体百分比/分块进度与结果，进度登记在 `asr_qwen/pipeline/progress.py`（内存表，任务 ID 键）。测试页走异步接口，展示整体进度条、阶段名、分块计数与实时耗时，结果区含句段表格（点击跳转播放）、关键词命中与 TXT/SRT/VTT/JSON 导出。
- **进度按阶段加权**：`progress.py` 的阶段序列与权重为 decode 0.10 → vad 0.08 → transcribe 0.55 → language 0.12 → postprocess 0.15，整体百分比 = 已完成阶段权重 + 当前阶段权重 × 阶段内比例；进度值与阶段序号只增不减。脚本投票后的二次转写通过 `ProgressReporter.subrange(low, high, alias="language")` 映射进 `language` 阶段尾部，因此不会让进度倒退或阶段跳回 `transcribe`。
- **转写输出结构**：`pipeline/localizer.py` 返回 `language`、`duration`、`title`、`body`、`text`、`segments`、`matched`、`stats`；`segments` 每项为 `index/text/start/end/duration`（序号从 1 起），`matched` 每项为 `rule/start/end/timestamp/segment_index/confidence`。改动输出结构需同步改 `localizer.py`、`text/keywords.py`、`text/sentences.py`、`api/testui.py` 与两份 README。

## 维护规则

项目结构、构建/测试命令、架构边界、开发约定或本文件记录的其他事实发生变化时，必须在同一次改动中同步更新本文件：用当前事实替换过期表述，不追加变更历史。详细事故复盘、性能对比、实验过程放入有链接的独立文档，仅任务相关时读取。修改已有内容前先提方案并征得用户同意，保留所有有效要求及其作用域。
