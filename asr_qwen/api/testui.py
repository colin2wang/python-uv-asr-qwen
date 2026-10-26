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
  :root {
    --bg: #f5f7fa; --card: #fff; --line: #e4e7ec; --text: #1f2328;
    --muted: #656d76; --brand: #2f6feb; --brand-dark: #1a52c0;
    --ok: #1a7f37; --err: #cf222e; --soft: #f6f8fa;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; padding: 24px 16px 48px; background: var(--bg); color: var(--text);
    font-family: system-ui, -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif;
    font-size: 15px; line-height: 1.6;
  }
  .wrap { max-width: 960px; margin: 0 auto; }
  header { display: flex; align-items: center; gap: 12px; margin-bottom: 18px; }
  h1 { font-size: 1.25rem; margin: 0; }
  .badge {
    font-size: 0.8rem; padding: 2px 10px; border-radius: 999px;
    border: 1px solid var(--line); background: var(--card); color: var(--muted);
  }
  .badge.ok { color: var(--ok); border-color: #b7e2c2; background: #eaf6ed; }
  .badge.err { color: var(--err); border-color: #f2c3c6; background: #fdf0f0; }
  .card {
    background: var(--card); border: 1px solid var(--line);
    border-radius: 10px; padding: 18px; margin-bottom: 16px;
  }
  h2 { font-size: 1rem; margin: 0 0 12px; }
  h3 { font-size: 0.9rem; margin: 18px 0 8px; color: var(--muted); }
  .muted { color: var(--muted); font-size: 0.85rem; }
  label { display: block; font-weight: 600; font-size: 0.85rem; margin-bottom: 4px; }
  input[type="text"] {
    width: 100%; padding: 7px 10px; border: 1px solid var(--line);
    border-radius: 6px; font: inherit; background: #fff; color: inherit;
  }
  input[type="text"]:focus { outline: 2px solid #cfe0fd; border-color: var(--brand); }
  .drop {
    border: 2px dashed var(--line); border-radius: 8px; padding: 20px;
    text-align: center; cursor: pointer; transition: border-color .15s, background .15s;
  }
  .drop:hover, .drop.drag { border-color: var(--brand); background: #f0f6ff; }
  .drop.has-file { border-style: solid; border-color: #b7e2c2; background: #f2fbf5; }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 14px; }
  button {
    padding: 7px 16px; border: 1px solid var(--line); border-radius: 6px;
    background: #fff; color: var(--text); font: inherit; cursor: pointer;
  }
  button:hover { border-color: #c8cfd8; }
  button.primary { background: var(--brand); border-color: var(--brand); color: #fff; }
  button.primary:hover { background: var(--brand-dark); }
  button:disabled { opacity: .55; cursor: not-allowed; }
  .actions { display: flex; align-items: center; gap: 10px; margin-top: 14px; }
  audio { display: block; width: 100%; margin-top: 14px; }
  .progress-card {
    margin-top: 16px; padding-top: 14px; border-top: 1px solid var(--line);
  }
  .progress-head {
    display: flex; justify-content: space-between; align-items: baseline;
    font-size: 0.9rem; font-weight: 600;
  }
  .track {
    height: 8px; background: var(--soft); border: 1px solid var(--line);
    border-radius: 999px; overflow: hidden; margin: 8px 0 6px;
  }
  .bar {
    height: 100%; width: 0; border-radius: 999px;
    background: linear-gradient(90deg, #4c8dff, var(--brand));
    transition: width .4s ease;
  }
  .progress-foot { display: flex; justify-content: space-between; }
  .chips { display: flex; flex-wrap: wrap; gap: 8px; }
  .chip {
    background: var(--soft); border: 1px solid var(--line); border-radius: 999px;
    padding: 3px 12px; font-size: 0.82rem;
  }
  .chip b { font-weight: 600; }
  .title-text { font-size: 1.05rem; font-weight: 700; margin: 0 0 6px; }
  .body-text { white-space: pre-wrap; margin: 0; }
  .empty { color: var(--muted); font-style: italic; }
  table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
  th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--line); }
  th { color: var(--muted); font-weight: 600; font-size: 0.8rem; }
  tbody tr { cursor: pointer; }
  tbody tr:hover { background: #f0f6ff; }
  td.time { font-variant-numeric: tabular-nums; white-space: nowrap; width: 1%; }
  td.idx { width: 1%; color: var(--muted); font-variant-numeric: tabular-nums; }
  .hit {
    display: inline-flex; align-items: center; gap: 6px; background: #fff8e6;
    border: 1px solid #f0d9a0; border-radius: 6px; padding: 3px 10px;
    margin: 0 6px 6px 0; font-size: 0.85rem; cursor: pointer;
  }
  .hit:hover { background: #fef2d6; }
  .toolbar { display: flex; flex-wrap: wrap; gap: 8px; }
  pre {
    background: var(--soft); border: 1px solid var(--line); border-radius: 6px;
    padding: 12px; overflow: auto; max-height: 320px; font-size: 0.82rem;
    white-space: pre-wrap; word-break: break-all; margin: 0;
  }
  .err-text { color: var(--err); }
  details { margin-top: 12px; }
  summary { cursor: pointer; font-size: 0.85rem; color: var(--muted); }
  @media (max-width: 640px) { .grid { grid-template-columns: 1fr; } }
</style>
</head>
<body>
<div class="wrap">

<header>
  <h1>Qwen3-ASR 转写定位</h1>
  <span class="badge" id="health">加载中…</span>
</header>

<section class="card">
  <form id="form">
    <input type="file" id="file" accept="audio/*,video/*" hidden>
    <div class="drop" id="drop">
      <strong>点击选择文件</strong>，或把音视频拖到这里
      <div class="muted" id="fileinfo">wav / mp3 / flac / ogg / m4a 等可解码格式</div>
    </div>
    <audio id="player" controls hidden></audio>
    <div class="grid">
      <div>
        <label for="question">定位关键词（可选，逗号分隔）</label>
        <input type="text" id="question" placeholder="例如：价格,退款">
      </div>
      <div>
        <label for="language">指定语种（可选，留空自动检测）</label>
        <input type="text" id="language" placeholder="例如：Chinese / English / yue">
      </div>
    </div>
    <div class="actions">
      <button type="submit" class="primary" id="submit">上传并转写</button>
      <button type="button" id="cancel" hidden>停止等待</button>
    </div>
  </form>

  <div class="progress-card" id="progressCard" hidden>
    <div class="progress-head">
      <span id="stageText">准备中…</span>
      <span id="percentText">0%</span>
    </div>
    <div class="track"><div class="bar" id="bar"></div></div>
    <div class="progress-foot">
      <span class="muted" id="chunks"></span>
      <span class="muted" id="elapsed">0.0s</span>
    </div>
  </div>
</section>

<section class="card" id="errorCard" hidden>
  <h2>转写失败</h2>
  <p class="err-text" id="errorText"></p>
</section>

<section class="card" id="result" hidden>
  <h2>结果</h2>
  <div class="chips" id="overview"></div>

  <h3>标题 / 正文</h3>
  <p class="title-text" id="title"></p>
  <p class="body-text" id="body"></p>

  <h3>句段（点击行跳转到该时间点）</h3>
  <table>
    <thead><tr><th>#</th><th>起止</th><th>时长</th><th>文本</th></tr></thead>
    <tbody id="segmentRows"></tbody>
  </table>

  <h3>关键词命中</h3>
  <div id="matched"></div>

  <h3>导出</h3>
  <div class="toolbar">
    <button type="button" id="copyText">复制全文</button>
    <button type="button" id="saveTxt">TXT</button>
    <button type="button" id="saveSrt">SRT</button>
    <button type="button" id="saveVtt">VTT</button>
    <button type="button" id="saveJson">JSON</button>
  </div>

  <details><summary>原始 JSON</summary><pre id="raw"></pre></details>
</section>

</div>

<script>
const $ = (id) => document.getElementById(id);
const state = { result: null, baseName: 'transcript', cancelled: false, timer: 0, start: 0 };

async function refreshHealth() {
  try {
    const res = await fetch('/health');
    const data = await res.json();
    const badge = $('health');
    badge.textContent = (data.loaded ? '模型已加载' : '模型未加载（503）')
      + ' · ' + data.device + ' · lid=' + (data.lid ? 'on' : 'off');
    badge.className = 'badge ' + (data.loaded ? 'ok' : 'err');
  } catch (e) {
    $('health').textContent = '服务不可达';
    $('health').className = 'badge err';
  }
}

function pad(value, length) {
  return String(value).padStart(length, '0');
}

function clock(seconds, separator) {
  const total = Math.max(0, Number(seconds) || 0);
  const ms = Math.round((total - Math.floor(total)) * 1000);
  return pad(Math.floor(total / 3600), 2) + ':' + pad(Math.floor((total % 3600) / 60), 2)
    + ':' + pad(Math.floor(total % 60), 2) + separator + pad(ms, 3);
}

function shortTime(seconds) {
  const total = Math.max(0, Number(seconds) || 0);
  return pad(Math.floor(total / 60), 2) + ':' + pad(Math.floor(total % 60), 2);
}

function humanSeconds(seconds) {
  const total = Math.max(0, Number(seconds) || 0);
  if (total < 60) return total.toFixed(1) + 's';
  return Math.floor(total / 60) + 'm' + pad(Math.floor(total % 60), 2) + 's';
}

function pickFile(file) {
  if (!file) return;
  $('player').src = URL.createObjectURL(file);
  $('player').hidden = false;
  $('drop').classList.add('has-file');
  const size = (file.size / 1048576).toFixed(2);
  $('fileinfo').textContent = file.name + ' · ' + size + ' MB';
  state.baseName = file.name.replace(/\\.[^.]+$/, '') || 'transcript';
}

$('drop').addEventListener('click', () => $('file').click());
$('file').addEventListener('change', () => pickFile($('file').files[0]));
['dragenter', 'dragover'].forEach((name) => $('drop').addEventListener(name, (ev) => {
  ev.preventDefault();
  $('drop').classList.add('drag');
}));
['dragleave', 'drop'].forEach((name) => $('drop').addEventListener(name, (ev) => {
  ev.preventDefault();
  $('drop').classList.remove('drag');
}));
$('drop').addEventListener('drop', (ev) => {
  const file = ev.dataTransfer.files[0];
  if (!file) return;
  const holder = new DataTransfer();
  holder.items.add(file);
  $('file').files = holder.files;
  pickFile(file);
});

function startTimer() {
  state.start = performance.now();
  stopTimer();
  state.timer = setInterval(() => {
    $('elapsed').textContent = ((performance.now() - state.start) / 1000).toFixed(1) + 's';
  }, 200);
}

function stopTimer() {
  if (state.timer) {
    clearInterval(state.timer);
    state.timer = 0;
  }
}

function resetProgress() {
  $('progressCard').hidden = false;
  $('bar').style.width = '0';
  $('percentText').textContent = '0%';
  $('stageText').textContent = '上传中…';
  $('chunks').textContent = '';
  $('elapsed').textContent = '0.0s';
}

function showProgress(job) {
  const percent = job.status === 'done' ? 100 : (job.percent || 0);
  $('bar').style.width = percent + '%';
  $('percentText').textContent = percent + '%';
  const label = job.status === 'done' ? '已完成' : (job.stage_label || '处理中');
  $('stageText').textContent = label;
  if (job.total > 1 && job.status !== 'done') {
    $('chunks').textContent = '分块 ' + job.done + '/' + job.total;
  } else if (job.status === 'done') {
    $('chunks').textContent = '耗时 ' + humanSeconds(job.elapsed_seconds);
  } else {
    $('chunks').textContent = '';
  }
}

function addChip(container, name, value) {
  const chip = document.createElement('span');
  chip.className = 'chip';
  const key = document.createElement('span');
  key.textContent = name + '：';
  const strong = document.createElement('b');
  strong.textContent = value;
  chip.appendChild(key);
  chip.appendChild(strong);
  container.appendChild(chip);
}

function renderOverview(data) {
  const overview = $('overview');
  overview.textContent = '';
  const stats = data.stats || {};
  addChip(overview, '语种', data.language || '未知');
  addChip(overview, '时长', humanSeconds(data.duration));
  addChip(overview, '句段', stats.segment_count != null ? stats.segment_count : (data.segments || []).length);
  addChip(overview, '字数', stats.char_count != null ? stats.char_count : (data.text || '').length);
  addChip(overview, '处理耗时', humanSeconds(stats.elapsed_seconds));
  if (stats.chunk_count != null) addChip(overview, '分块', stats.chunk_count);
}

function seek(seconds) {
  const player = $('player');
  if (!player.src) return;
  player.currentTime = Math.max(0, Number(seconds) || 0);
  player.play().catch(() => {});
}

function renderSegments(segments) {
  const rows = $('segmentRows');
  rows.textContent = '';
  segments.forEach((segment) => {
    const tr = document.createElement('tr');
    const cells = [
      segment.index,
      shortTime(segment.start) + ' → ' + shortTime(segment.end),
      shortTime(segment.duration),
      segment.text,
    ];
    cells.forEach((value, column) => {
      const td = document.createElement('td');
      td.textContent = value;
      if (column === 0) td.className = 'idx';
      if (column < 3 && column > 0) td.className = 'time';
      tr.appendChild(td);
    });
    tr.addEventListener('click', () => seek(segment.start));
    rows.appendChild(tr);
  });
  if (!segments.length) {
    const tr = document.createElement('tr');
    const td = document.createElement('td');
    td.colSpan = 4;
    td.className = 'empty';
    td.textContent = '没有可展示的句段（音频可能无人声）';
    tr.appendChild(td);
    rows.appendChild(tr);
  }
}

function renderMatched(matched) {
  const holder = $('matched');
  holder.textContent = '';
  if (!matched || !matched.length) {
    const span = document.createElement('span');
    span.className = 'muted';
    span.textContent = '未填入关键词或无命中';
    holder.appendChild(span);
    return;
  }
  matched.forEach((hit) => {
    const item = document.createElement('span');
    item.className = 'hit';
    item.textContent = hit.rule + ' · ' + shortTime(hit.start)
      + (hit.segment_index ? ' · 第' + hit.segment_index + '句' : '');
    item.addEventListener('click', () => seek(hit.start));
    holder.appendChild(item);
  });
}

function renderResult(data) {
  state.result = data;
  renderOverview(data);
  const title = $('title');
  title.textContent = data.title || '';
  title.hidden = !data.title;
  const body = $('body');
  body.textContent = data.body || data.text || '';
  if (!data.body && !data.text) {
    body.textContent = '（无转写内容）';
    body.className = 'body-text empty';
  } else {
    body.className = 'body-text';
  }
  renderSegments(data.segments || []);
  renderMatched(data.matched || []);
  $('raw').textContent = JSON.stringify(data, null, 2);
  $('errorCard').hidden = true;
  $('result').hidden = false;
}

function renderError(message) {
  $('result').hidden = true;
  $('errorText').textContent = message;
  $('errorCard').hidden = false;
}

function saveFile(name, content, mime) {
  const blob = new Blob([content], { type: mime + ';charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = name;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function toSrt(segments) {
  return segments.map((segment, index) => [
    index + 1,
    clock(segment.start, ',') + ' --> ' + clock(segment.end, ','),
    segment.text,
  ].join('\\n')).join('\\n\\n') + '\\n';
}

function toVtt(segments) {
  return 'WEBVTT\\n\\n' + segments.map((segment) => [
    clock(segment.start, '.') + ' --> ' + clock(segment.end, '.'),
    segment.text,
  ].join('\\n')).join('\\n\\n') + '\\n';
}

function toTxt(data) {
  const lines = [];
  if (data.title) lines.push(data.title);
  if (data.body || data.text) lines.push(data.body || data.text);
  return lines.join('\\n\\n') + '\\n';
}

function bindExport() {
  $('copyText').addEventListener('click', async () => {
    const content = toTxt(state.result || {});
    try {
      await navigator.clipboard.writeText(content);
      $('copyText').textContent = '已复制';
    } catch (e) {
      $('copyText').textContent = '复制失败';
    }
    setTimeout(() => { $('copyText').textContent = '复制全文'; }, 1500);
  });
  $('saveTxt').addEventListener('click', () => {
    saveFile(state.baseName + '.txt', toTxt(state.result || {}), 'text/plain');
  });
  $('saveSrt').addEventListener('click', () => {
    saveFile(state.baseName + '.srt', toSrt((state.result || {}).segments || []), 'text/plain');
  });
  $('saveVtt').addEventListener('click', () => {
    saveFile(state.baseName + '.vtt', toVtt((state.result || {}).segments || []), 'text/plain');
  });
  $('saveJson').addEventListener('click', () => {
    saveFile(state.baseName + '.json', JSON.stringify(state.result || {}, null, 2), 'application/json');
  });
}

async function pollJob(jobId) {
  for (;;) {
    if (state.cancelled) return null;
    const res = await fetch('/asr/jobs/' + jobId, { cache: 'no-store' });
    const job = await res.json();
    if (!res.ok) throw new Error(job.detail || res.statusText);
    showProgress(job);
    if (job.status === 'done') {
      stopTimer();
      $('elapsed').textContent = humanSeconds(job.elapsed_seconds);
      return job.result;
    }
    if (job.status === 'error') throw new Error(job.error || '任务失败');
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

  state.cancelled = false;
  $('submit').disabled = true;
  $('cancel').hidden = false;
  $('result').hidden = true;
  $('errorCard').hidden = true;
  resetProgress();
  startTimer();
  try {
    const res = await fetch('/asr/jobs', { method: 'POST', body });
    const created = await res.json();
    if (!res.ok) throw new Error(created.detail || res.statusText);
    showProgress(created);
    const result = await pollJob(created.job_id);
    if (result) renderResult(result);
  } catch (e) {
    renderError(e.message || String(e));
  } finally {
    stopTimer();
    $('cancel').hidden = true;
    $('submit').disabled = false;
    refreshHealth();
  }
});

$('cancel').addEventListener('click', () => {
  state.cancelled = true;
  $('cancel').hidden = true;
  $('stageText').textContent = '已停止等待（服务端继续处理）';
});

bindExport();
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
