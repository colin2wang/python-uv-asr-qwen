# Qwen3-ASR 转写定位服务

[English](README.md) | **简体中文**

基于 FastAPI 的语音转写定位服务：上传音视频文件，使用 Qwen3-ASR-1.7B 与强制对齐模型
一次产出**多语种转写、句段时间戳、关键词时间定位、标题与正文拆分**。

## 特性

- **多语种转写**：Qwen3-ASR-1.7B（约 30 种语言），GPU 推理。
- **句段带原文标点**：句段文本取自模型全文（标点与空格照抄），时间戳来自与 token 序列的
  对齐（`difflib` 序列匹配；标点/空白不消耗 token，规范化差异只会让个别字符拿不到时间，
  不会整体错位）。断句按句末标点，以及 `sentence.max_chars` /
  `sentence.max_duration_seconds` 上限——对齐 token 流**不含标点**，全文也无标点时靠上限
  切分；`sentence.min_gap_seconds` 可按停顿断句（默认 `0` 关闭——唱歌拖腔会产生碎片）。
  每段带 `start`/`end` 秒级时间戳，非法 token 时间戳按前后边界插值修复。
- **自动语种判定**：优先采用模型输出；唱歌音频走「脚本投票」兜底
  （西里尔 / 汉字 / 假名 / 谚文，同一脚本命中 ≥2 次才采信）；中文文本中检出粤语专用字时
  升级为 `Cantonese`。
- **关键词定位**：逗号分隔的查询词（如 `价格,退款`）在 token 拼接串上定位并映射到命中
  时间区间（查询词内部空格自动忽略，`killing me` 可命中英文歌词）。
- **标题 / 正文拆分**：规则优先（`标题：` 标记、首行、首句或前 `title.max_words` 个词），
  仅当规则结果不像标题时才调用 OpenAI 兼容 LLM；标题始终是转写原文的**精确前缀**，
  不翻译、不改写。
- **整段转写（默认不分块）**：整段音频一次送入模型 —— 分块会把跨块的句子从中间切断，
  且每块独立转写会丢失上下文，导致句末标点缺失、语句被切开。把 `audio.max_chunk_seconds`
  设为 > 0 可恢复「能量 VAD 找静音边界 → 分块 → 拼接时间轴」的行为。
- **同步 + 异步接口**：`POST /asr/localize` 同步返回；`POST /asr/jobs` 立即返回任务 ID，
  可轮询阶段、整体百分比、分块进度与耗时。
- **内置测试页面**：`/ui`，无前端构建、无新增依赖；展示整体进度条与阶段名，结果区可点击
  句段跳转播放，并导出 TXT / SRT / VTT / JSON。
- **配置零默认值**：`asr-qwen.yml` 字段全必填，缺失或类型错误直接抛 `ConfigError`；
  模型权重缺失时启动自动从 ModelScope 下载。

## 处理流程

```
上传 ──> audio/io.py       解码并重采样为单声道 16 kHz（torchaudio/torchcodec，必要时回退 ffmpeg CLI）
     ──> pipeline/transcribe  整段一次转写（audio.max_chunk_seconds > 0 时才 VAD 分块）
     ──> language/detector    语种归一化、脚本投票兜底、粤语判定
     ──> text/sentences       合并为带时间戳的句段（长度/时长上限，标点与停顿可选）
     ──> text/keywords        逗号分隔查询词 → 命中时间区间
     ──> text/title           规则拆分，必要时 LLM 修正（标题必须是原文前缀）
```

SenseVoice 语种识别模型（`lid.enabled`）在启动时加载，加载状态由 `/health` 返回；
脚本投票的采样窗口复用 `lid.segment_seconds`。

包内依赖方向单向向下：`api` → `pipeline` → `models` / `audio` / `language` / `text` / `config`。

## 环境要求

| 项目 | 说明 |
| --- | --- |
| Python | ≥ 3.12 |
| 依赖管理 | [uv](https://docs.astral.sh/uv/) |
| GPU | 可用 CUDA 驱动的 NVIDIA 显卡（torch 固定在 PyTorch `cu128` 索引） |
| FFmpeg | Windows 上需安装 **shared** 版并把 `bin` 加入 `PATH`，`torchcodec` 解码 mp3/m4a/ogg 时必需 |
| 可选 | `funasr`（`lid` 可选组），`lid.enabled: true` 时必需 |

torch/torchaudio 经 `pyproject.toml` 的 `tool.uv.sources` 从 CUDA 12.8 索引安装，
其余依赖走清华镜像。

## 快速开始

```powershell
# 1. 安装依赖（lid.enabled 为 true 时加 --extra lid）
uv sync --extra lid

# 2. 检查配置 asr-qwen.yml —— 所有字段必填

# 3. 启动服务（首次启动会把缺失的模型下载到 qwen-models/）
uv run main.py
```

启动后打印两个地址：

```
API      http://127.0.0.1:8010/docs
测试页面 http://127.0.0.1:8010/ui
```

其他入口：

```powershell
uv run asr-qwen                                  # 控制台脚本，行为一致
uv run uvicorn asr_qwen.server:app --port 8010   # server.workers > 1 时服务自动改为该方式
```

模型仅在配置目录不存在或为空时从 ModelScope 下载：

| 本地路径（`asr-qwen.yml`） | ModelScope 模型 ID |
| --- | --- |
| `model.asr_path` | `Qwen/Qwen3-ASR-1.7B` |
| `model.aligner_path` | `Qwen/Qwen3-ForcedAligner-0.6B` |
| `lid.model_path` | `iic/SenseVoiceSmall`（`lid.enabled: false` 时跳过） |

## 配置说明

配置定位顺序：显式参数 → `ASR_CONFIG_PATH` 环境变量 → 项目根目录 → 包目录 →
当前工作目录，取第一个存在的文件。文件内的相对路径相对于该 YAML 所在目录解析。

| 配置项 | 含义 |
| --- | --- |
| `model.asr_path` | Qwen3-ASR 模型目录 |
| `model.aligner_path` | 强制对齐模型目录（时间戳来源） |
| `model.dtype` | torch dtype 名称，如 `float16` |
| `model.device` | torch 设备，如 `cuda:0` |
| `model.max_inference_batch_size` | 解码批大小 |
| `lid.enabled` | 是否加载 SenseVoiceSmall 做语种识别 |
| `lid.model_path` | SenseVoiceSmall 目录 |
| `lid.device` | 语种识别设备，如 `cpu` |
| `lid.segment_seconds` | 语种采样 / 脚本投票使用的音频窗口时长 |
| `vad.frame_ms` / `hop_ms` | 能量分析的帧长与帧移（仅分块时使用） |
| `vad.threshold_db` | 语音判定阈值（dBFS） |
| `vad.min_silence_ms` | 短于该值的间隔视为语音 |
| `vad.min_speech_ms` | 短于该值的语音段被丢弃 |
| `audio.sample_rate` | 目标单声道采样率（建议 16000） |
| `audio.max_chunk_seconds` | `0` = 整段送模型（默认）；`> 0` = 超过该时长才按 VAD 静音点分块 |
| `sentence.min_gap_seconds` | 相邻 token 停顿达到该值即断句；`0` 关闭（唱歌拖腔会产生碎片） |
| `sentence.max_chars` | 句段字符数上限，`0` 表示不限制 |
| `sentence.max_duration_seconds` | 句段时长上限（秒），`0` 表示不限制 |
| `title.max_chars` | 规则拆分可接受的标题长度上限 |
| `title.max_words` | 规则拆分可接受的标题词数上限 |
| `title.llm.base_url` | OpenAI 兼容接口地址 |
| `title.llm.model` | 标题修正使用的模型名 |
| `title.llm.api_key` | 密钥；留空则不调用 LLM，只用规则 |
| `title.llm.timeout_seconds` | LLM 请求超时 |
| `server.title` / `version` | OpenAPI 元信息 |
| `server.host` / `port` | 监听地址；`0.0.0.0`/`::` 会按 `127.0.0.1` 打印提示 |
| `server.log_level` | uvicorn 日志级别 |
| `server.workers` | 工作进程数；> 1 时改为 `asr_qwen.server:app` 启动方式 |

## 接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/health` | 返回 `status`、`loaded`、`lid`、`model`、`device` |
| `POST` | `/asr/localize` | 同步转写（multipart） |
| `POST` | `/asr/jobs` | 创建后台任务，返回 `{"job_id": "..."}` |
| `GET` | `/asr/jobs/{job_id}` | 查询状态、阶段、整体百分比、分块进度与结果 |
| `GET` | `/ui` | 内置测试页面 |
| `GET` | `/docs` | OpenAPI 文档 |

两个转写接口的 multipart 字段：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `file` | 是 | 音视频文件，解码器支持的格式均可（wav / mp3 / flac / ogg / m4a …） |
| `question` | 否 | 逗号分隔的关键词查询 |
| `language` | 否 | 语种名或代码（`Chinese`、`en`、`yue` …），留空自动判定 |

模型未加载完成时，两个转写接口均返回 `503`。

`vad.*` 与 `audio.max_chunk_seconds` 仅在分块模式下生效：默认整段转写，把
`audio.max_chunk_seconds` 设为 > 0 即切回分块模式。

### 同步调用

```powershell
curl.exe -X POST http://127.0.0.1:8010/asr/localize `
  -F "file=@sample.mp3" `
  -F "question=价格,退款" `
  -F "language="
```

### 异步调用

```powershell
$job = curl.exe -s -X POST http://127.0.0.1:8010/asr/jobs -F "file=@sample.mp3"
# {"job_id":"8f1c02a9d3e4"}

curl.exe -s http://127.0.0.1:8010/asr/jobs/8f1c02a9d3e4
```

任务状态：`status` ∈ `queued` / `running` / `done` / `error`，
`stage` ∈ `queued` / `decode` / `vad` / `transcribe` / `language` / `postprocess`
（附带 `stage_label` 中文名），`percent` 为整体百分比、`done`/`total` 为分块计数
（未分块时均为 0），`elapsed_seconds` 为任务已运行时长。

```json
{
  "job_id": "8f1c02a9d3e4",
  "status": "running",
  "stage": "transcribe",
  "stage_label": "转写中",
  "progress": 0.4128,
  "percent": 41,
  "done": 3,
  "total": 10,
  "elapsed_seconds": 26.4,
  "result": null,
  "error": null
}
```

整体百分比按阶段加权计算（decode 10% → vad 8% → transcribe 55% → language 12% →
postprocess 15%），且只增不减：唱歌音频触发脚本投票后的二次转写，其进度被映射进
`language` 阶段尾部，因此进度条不会倒退。完成时带 `result`（结构同下），失败时带
`error`。进度表为内存结构，超过一小时的任务会在下次创建任务时清理。

### 返回结构

```json
{
  "language": "Chinese",
  "duration": 4.86,
  "title": "今天的主题是价格。",
  "body": "下面看三个例子。",
  "text": "今天的主题是价格。下面看三个例子。",
  "segments": [
    {
      "index": 1, "text": "今天的主题是价格。",
      "start": 0.12, "end": 2.4, "duration": 2.28
    },
    {
      "index": 2, "text": "下面看三个例子。",
      "start": 2.4, "end": 4.86, "duration": 2.46
    }
  ],
  "matched": [
    {
      "rule": "价格", "start": 0.12, "end": 1.4,
      "timestamp": [0.12, 1.4], "segment_index": 1, "confidence": 1.0
    }
  ],
  "stats": {
    "sample_rate": 16000,
    "chunk_count": 1,
    "segment_count": 2,
    "char_count": 20,
    "elapsed_seconds": 3.42
  }
}
```

- `language` — 模型判定的语种，经脚本投票 / 粤语规则修正后的结果。
- `duration` — 音频时长（秒）。
- `text` — 全文转写。
- `segments` — 由对齐 token 合并出的句段：`index` 从 1 起的序号，`start`/`end`/
  `duration` 单位为秒。
- `matched` — 每个关键词命中项：`rule` 对应查询词，`start`/`end`（等同 `timestamp`）
  为命中区间，`segment_index` 为所属句段序号，`confidence` 恒为 1.0（子串精确匹配）。
- `title` / `body` — `title` 是 `text` 的精确前缀，两者拼接可还原全文。
- `stats` — 处理元信息：采样率、分块数、句段数、字数与流水线耗时。

## 目录结构

```
asr_qwen/
  api/        FastAPI 装配（app.py）、路由（routes.py）、内嵌测试页（testui.py）
  audio/      io.py（解码/重采样/临时文件）、vad.py（能量 VAD 与分块）
  config/     settings.py（frozen dataclass）、loader.py（严格 YAML 校验）
  language/   codes.py（语种码表）、detector.py（脚本投票、粤语判定）
  models/     registry.py（模型生命周期）、download.py（ModelScope 下载）
  pipeline/   localizer.py（编排）、transcribe.py、progress.py（任务进度表）
  text/       sentences.py、keywords.py、title.py
  server.py   进程入口（uvicorn）
asr-qwen.yml  唯一配置文件
main.py       便捷启动脚本
```

## 注意事项与排错

- **配置零默认值**：新增配置项需同时改 `config/settings.py`、`config/loader.py` 与 `asr-qwen.yml`。
- **mp3/m4a 解码报 `ImportError`（Windows）**：安装 FFmpeg **shared** 版并把 `bin` 加入
  `PATH`；`audio/io.py` 在 `torchcodec` 失败时还会回退到 `ffmpeg` 命令行转封装。
- **纯 CPU 环境**：`tool.uv.sources` 之所以把 torch/torchaudio 固定到 CUDA 12.8 索引，
  是因为 PyPI 在 Windows 上只提供 CPU 轮子；改版本或换 CPU 轮子前先确认索引里存在对应文件。
- **模型权重不入库**：`qwen-models/` 已被 `.gitignore` 忽略，首次启动自动下载（数 GB，
  需要可用的 ModelScope 网络访问）。
- **本仓库暂无测试套件和 lint 配置**，改动后请自行静态核对或直接启动服务验证。
- **部署范围**：`/ui` 无鉴权，仅供本地调试；对外暴露时请置于网关之后。
