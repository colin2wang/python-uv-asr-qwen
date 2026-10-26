"""内置测试页面：上传媒体文件调用转写定位接口。"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from .routes import _context

router = APIRouter()

_PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Qwen3-ASR 测试页面</title>
<style>
  body { font-family: system-ui, sans-serif; max-width: 860px; margin: 24px auto; padding: 0 16px; color: #1f2328; }
  h1 { font-size: 1.3rem; }
  .card { border: 1px solid #d0d7de; border-radius: 8px; padding: 16px; margin-bottom: 16px; }
  .health span { margin-right: 16px; }
  label { display: block; margin: 8px 0 4px; font-weight: 600; }
  input[type="text"] { width: 100%; box-sizing: border-box; padding: 6px 8px; border: 1px solid #d0d7de; border-radius: 6px; }
  button { margin-top: 12px; padding: 8px 20px; border: 0; border-radius: 6px; background: #1f6feb; color: #fff; cursor: pointer; }
  button:disabled { background: #94a3b8; cursor: wait; }
  audio { display: block; margin-top: 12px; width: 100%; }
  pre { background: #f6f8fa; padding: 12px; border-radius: 6px; overflow: auto; white-space: pre-wrap; }
  .err { color: #cf222e; }
  .muted { color: #57606a; font-size: 0.85rem; }
  .progress { margin-top: 12px; height: 8px; background: #d0d7de; border-radius: 4px; overflow: hidden; }
  .progress .bar { height: 100%; width: 0; background: #1f6feb; transition: width 0.3s; }
  .progress.indeterminate .bar { width: 40%; animation: slide 1.2s infinite linear; }
  @keyframes slide { from { transform: translateX(-100%); } to { transform: translateX(350%); } }
</style>
</head>
<body>
<h1>Qwen3-ASR 转写定位测试</h1>

<div class="card health">
  <strong>服务状态</strong>：<span id="health">加载中…</span>
</div>

<div class="card">
  <form id="form">
    <label for="file">媒体文件（wav / mp3 / flac / ogg / m4a 等可解码格式）</label>
    <input type="file" id="file" accept="audio/*,video/*" required>
    <audio id="player" controls hidden></audio>
    <label for="question">定位关键词（可选）</label>
    <input type="text" id="question" placeholder="例如：价格">
    <label for="language">指定语种（可选，留空自动检测）</label>
    <input type="text" id="language" placeholder="例如：Chinese / English / yue">
    <button type="submit" id="submit">上传并转写</button>
    <span class="muted" id="elapsed"></span>
    <div class="progress" id="progress" hidden><div class="bar" id="bar"></div></div>
    <span class="muted" id="stage"></span>
  </form>
</div>

<div class="card" id="result" hidden>
  <h2>结果</h2>
  <p><strong>语种</strong>：<span id="lang"></span></p>
  <p><strong>标题</strong>：<span id="title"></span></p>
  <p><strong>全文</strong>：<span id="text"></span></p>
  <h3>句段</h3>
  <pre id="segments"></pre>
  <h3>关键词命中</h3>
  <pre id="matched"></pre>
  <details><summary>原始 JSON</summary><pre id="raw"></pre></details>
</div>

<script>
const $ = (id) => document.getElementById(id);

async function refreshHealth() {
  try {
    const res = await fetch('/health');
    const data = await res.json();
    $('health').textContent =
      (data.loaded ? '模型已加载' : '模型未加载（503）') +
      ' · device=' + data.device + ' · lid=' + (data.lid ? 'on' : 'off');
    $('health').className = data.loaded ? '' : 'err';
  } catch (e) {
    $('health').textContent = '服务不可达：' + e;
    $('health').className = 'err';
  }
}

$('file').addEventListener('change', () => {
  const file = $('file').files[0];
  if (file) {
    $('player').src = URL.createObjectURL(file);
    $('player').hidden = false;
  }
});

const STAGES = {
  queued: '排队中…',
  decode: '解码音频…',
  transcribe: '转写中…',
  postprocess: '后处理…',
};

function showProgress(job) {
  const bar = $('progress');
  bar.hidden = false;
  const label = STAGES[job.stage] || job.stage;
  if (job.status === 'done') {
    bar.classList.remove('indeterminate');
    $('bar').style.width = '100%';
    $('stage').textContent = '完成';
  } else if (job.total > 0) {
    bar.classList.remove('indeterminate');
    $('bar').style.width = Math.round(100 * job.done / job.total) + '%';
    $('stage').textContent = label + ' ' + job.done + '/' + job.total;
  } else {
    bar.classList.add('indeterminate');
    $('bar').style.width = '40%';
    $('stage').textContent = label;
  }
}

function hideProgress() {
  $('progress').hidden = true;
  $('progress').classList.remove('indeterminate');
  $('bar').style.width = '0';
  $('stage').textContent = '';
}

function renderResult(data) {
  $('lang').textContent = data.language;
  $('title').textContent = data.title;
  $('text').textContent = data.text;
  $('segments').textContent = JSON.stringify(data.segments, null, 2);
  $('matched').textContent = JSON.stringify(data.matched, null, 2);
  $('raw').textContent = JSON.stringify(data, null, 2);
  $('result').hidden = false;
}

function renderError(message) {
  $('result').hidden = false;
  $('lang').textContent = $('title').textContent = $('text').textContent = '';
  $('segments').textContent = $('matched').textContent = '';
  $('raw').textContent = '请求失败：' + message;
}

async function pollJob(jobId, start) {
  for (;;) {
    const res = await fetch('/asr/jobs/' + jobId);
    const job = await res.json();
    if (!res.ok) throw new Error(job.detail || res.statusText);
    showProgress(job);
    if (job.status === 'done') {
      renderResult(job.result);
      return;
    }
    if (job.status === 'error') throw new Error(job.error);
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
}

$('form').addEventListener('submit', async (ev) => {
  ev.preventDefault();
  const file = $('file').files[0];
  if (!file) return;
  const body = new FormData();
  body.append('file', file, file.name);
  if ($('question').value.trim()) body.append('question', $('question').value.trim());
  if ($('language').value.trim()) body.append('language', $('language').value.trim());

  $('submit').disabled = true;
  const start = performance.now();
  hideProgress();
  try {
    const res = await fetch('/asr/jobs', { method: 'POST', body });
    const created = await res.json();
    if (!res.ok) throw new Error(created.detail || res.statusText);
    await pollJob(created.job_id, start);
  } catch (e) {
    renderError(e);
  } finally {
    $('elapsed').textContent = '耗时 ' + ((performance.now() - start) / 1000).toFixed(1) + 's';
    $('submit').disabled = false;
    refreshHealth();
  }
});

refreshHealth();
</script>
</body>
</html>
"""


@router.get("/ui", response_class=HTMLResponse, include_in_schema=False)
def test_ui(request: Request) -> HTMLResponse:
    """内置测试页面；仅本地调试用，不走鉴权。"""
    _context(request)  # 确认应用上下文已装配
    return HTMLResponse(_PAGE)
