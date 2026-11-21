const categories = {
  weak_forms: "弱读",
  linking: "连读",
  elision: "省音",
  sound_change: "变音",
  assimilation: "变音",
  reduction: "缩读",
};
const find = (id) => document.getElementById(id);
const terminal = new Set(["success", "partial", "failed"]);
let currentJob;
let busy = false;
let activeRun = 0;
const player = find("clip-player");
let audioFile;
let mediaUrl;
let playable;
let playbackId = 0;
let playbackEnd = null;
let openPractice;
let songDuration = 0;

function updatePlayer() {
  const current = Number.isFinite(player.currentTime) ? player.currentTime : 0;
  const duration = Number.isFinite(player.duration) ? player.duration : songDuration;
  find("track-position").max = duration || 1;
  find("track-position").value = current;
  find("track-position").setAttribute("aria-valuetext", timestamp(current) + " / " + timestamp(duration));
  find("track-time").textContent = timestamp(current) + " / " + timestamp(duration);
  find("track-toggle").textContent = player.paused ? "▶" : "Ⅱ";
  find("track-toggle").setAttribute("aria-label", player.paused ? "播放歌曲" : "暂停歌曲");
}

function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

function timestamp(seconds) {
  const minutes = Math.floor(seconds / 60);
  const remainder = Math.floor(seconds % 60);
  return [minutes, remainder].map((value) => String(value).padStart(2, "0")).join(":");
}

function timeRange(line) {
  if (line.start_seconds === null && line.search_window) {
    return "约 " + line.search_window.map(timestamp).join("–");
  }
  return line.start_seconds === null ? "" :
    (line.needs_review ? "约 " : "") + timestamp(line.start_seconds) + "–" + timestamp(line.end_seconds);
}

function status(text, percent, completed = false) {
  find("activity").hidden = false;
  find("status").textContent = text;
  const bar = find("progress");
  bar.hidden = completed;
  if (percent === null) bar.removeAttribute("value");
  else bar.value = percent;
}

function stopClip() {
  playbackId += 1;
  playbackEnd = null;
  player.pause();
  find("stop-clip").hidden = true;
}

function selectAudio(file) {
  stopClip();
  player.removeAttribute("src");
  player.load();
  if (mediaUrl) URL.revokeObjectURL(mediaUrl);
  mediaUrl = undefined;
  playable = undefined;
  audioFile = file;
  find("playback").hidden = true;
  songDuration = 0;
  updatePlayer();
}

function loadMedia(blob) {
  if (mediaUrl) URL.revokeObjectURL(mediaUrl);
  mediaUrl = URL.createObjectURL(blob);
  return new Promise((resolve, reject) => {
    const clean = () => {
      player.removeEventListener("loadedmetadata", loaded);
      player.removeEventListener("error", failed);
    };
    const loaded = () => { clean(); resolve(); };
    const failed = () => { clean(); reject(new Error("浏览器无法解码。")); };
    player.addEventListener("loadedmetadata", loaded);
    player.addEventListener("error", failed);
    player.src = mediaUrl;
    player.load();
  });
}

async function prepareMedia(file) {
  const header = new Uint8Array(await file.slice(4, 8).arrayBuffer());
  const isMp4 = String.fromCharCode(...header) === "ftyp";
  try {
    await loadMedia(file.slice(0, file.size, isMp4 ? "audio/mp4" : "audio/mpeg"));
  } catch {
    if (file !== audioFile) throw new Error("录音已切换。");
    const response = await fetch("/api/preview", {
      method: "POST", headers: {"Content-Type": "audio/mpeg"}, body: file,
    });
    if (!response.ok) throw new Error("无法准备试听音频。");
    const blob = await response.blob();
    if (file !== audioFile) throw new Error("录音已切换。");
    await loadMedia(blob);
  }
}

async function playClip(startTime, endTime, number) {
  if (!audioFile) return;
  stopClip();
  if (!Number.isFinite(startTime) || !Number.isFinite(endTime) || startTime < 0 || endTime <= startTime) {
    find("playback").hidden = false;
    find("playback-message").textContent = "请输入有效的起止时间。";
    return;
  }
  const requestId = playbackId;
  find("playback").hidden = false;
  find("playback-message").textContent = "正在准备第 " + (number + 1) + " 行的试听…";
  try {
    playable ||= prepareMedia(audioFile);
    await playable;
    if (requestId !== playbackId) return;
    if (startTime >= player.duration) throw new Error("起始时间超出录音。");
    player.currentTime = startTime;
    playbackEnd = Math.min(endTime, player.duration);
    await player.play();
    if (requestId !== playbackId) return;
    find("playback-message").textContent = "正在试听第 " + (number + 1) + " 行";
    find("stop-clip").hidden = false;
    function stopAtBoundary() {
      if (requestId !== playbackId || player.paused) return;
      checkPlaybackBoundary();
      if (playbackEnd !== null) requestAnimationFrame(stopAtBoundary);
    }
    requestAnimationFrame(stopAtBoundary);
  } catch (error) {
    if (requestId !== playbackId) return;
    stopClip();
    if (player.readyState === 0) playable = undefined;
    find("playback-message").textContent = error.message || "试听失败。";
  }
}

function checkPlaybackBoundary() {
  if (playbackEnd !== null && (player.currentTime >= playbackEnd || player.ended)) {
    stopClip();
    find("playback-message").textContent = "试听结束";
  }
}

player.addEventListener("timeupdate", checkPlaybackBoundary);
player.addEventListener("ended", checkPlaybackBoundary);
for (const event of ["timeupdate", "loadedmetadata", "play", "pause", "ended"]) {
  player.addEventListener(event, updatePlayer);
}
find("track-toggle").addEventListener("click", async () => {
  if (!audioFile) return;
  if (!player.paused) {
    player.pause();
    return;
  }
  const requestId = ++playbackId;
  playbackEnd = null;
  find("stop-clip").hidden = true;
  try {
    playable ||= prepareMedia(audioFile);
    await playable;
    if (requestId !== playbackId) return;
    await player.play();
    if (requestId !== playbackId) {
      player.pause();
      return;
    }
    find("playback").hidden = true;
  } catch {
    playable = undefined;
    find("playback").hidden = false;
    find("playback-message").textContent = "音频暂时无法播放，请再试一次。";
  }
});
find("track-position").addEventListener("input", async (event) => {
  if (!audioFile) return;
  const next = Number(event.target.value);
  const requestId = ++playbackId;
  playbackEnd = null;
  find("stop-clip").hidden = true;
  try {
    playable ||= prepareMedia(audioFile);
    await playable;
    if (requestId !== playbackId) return;
    player.currentTime = next;
    updatePlayer();
  } catch {
    playable = undefined;
    find("playback").hidden = false;
    find("playback-message").textContent = "音频暂时无法播放，请再试一次。";
  }
});
find("stop-clip").addEventListener("click", () => {
  stopClip();
  find("playback-message").textContent = "已停止播放";
});

function setBusy(active) {
  busy = active;
  for (const control of document.querySelectorAll(
    "#audio, #upload-button, #change-song, #text-button, #retry-button, .edit-button, .line-editor fieldset"
  )) control.disabled = active;
}

async function request(path, options) {
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "请求失败。");
  return data;
}

function postJson(path, data) {
  return request(path, { method: "POST", headers: { "Content-Type": "application/json" },
                         body: JSON.stringify(data) });
}

async function start(send, message, { preserve = false, editNote = null, editedLine = null } = {}) {
  if (busy) return;
  const run = ++activeRun;
  const previousJob = currentJob;
  setBusy(true);
  if (!preserve) {
    currentJob = undefined;
    find("results").hidden = true;
  }
  if (editNote) editNote.textContent = message;
  else status(message, null);
  try {
    const { id } = await send();
    if (run !== activeRun) return;
    let job;
    do {
      job = await request("/api/jobs/" + id);
      if (run !== activeRun) return;
      const completed = terminal.has(job.status);
      if (!completed) {
        if (!editNote) status(job.message, job.progress);
        await new Promise((resolve) => setTimeout(resolve, 450));
      }
    } while (!terminal.has(job.status));
    if (!job.lines?.length) throw new Error(job.message);
    currentJob = id;
    find("activity").hidden = true;
    const counts = renderJob(job);
    if (!preserve) find("results").focus();
    if (job.analysis) {
      postJson("/api/jobs/" + id + "/rendered", counts).catch(() => {});
    }
  } catch (error) {
    if (run !== activeRun) return;
    if (preserve) currentJob = previousJob;
    if (editNote) editNote.textContent = error.message;
    else status("处理未完成，请重试上传。", null, true);
  } finally {
    if (run === activeRun) {
      setBusy(false);
      find("audio").value = "";
      if (editedLine !== null) {
        const row = find("annotated-lyrics").children[editedLine];
        if (row && !row.querySelector(".line-editor")) row.querySelector(".edit-button").focus();
      }
    }
  }
}

find("home-button").addEventListener("click", () => {
  activeRun += 1;
  stopClip();
  player.loop = false;
  closePractice();
  document.body.classList.remove("is-learning");
  find("results").hidden = true;
  find("activity").hidden = true;
  find("change-song").hidden = true;
  find("audio").value = "";
  setBusy(false);
  window.scrollTo({ top: 0, behavior: "instant" });
});

function spokenContents(element, ipa) {
  if (!ipa.emphasis) {
    element.textContent = ipa.spoken;
    return;
  }
  const index = ipa.spoken.indexOf(ipa.emphasis);
  if (index < 0) {
    element.textContent = ipa.spoken;
    return;
  }
  element.append(ipa.spoken.slice(0, index), node("mark", "", ipa.emphasis),
                 ipa.spoken.slice(index + ipa.emphasis.length));
}

function closePractice() {
  if (!openPractice) return;
  const { fragment, slot } = openPractice;
  slot.hidden = true;
  slot.replaceChildren();
  for (const control of slot.parentElement.querySelectorAll("[aria-expanded=true]")) {
    control.setAttribute("aria-expanded", "false");
  }
  openPractice = undefined;
}

function alignPractice() {
  if (!openPractice) return;
  const { fragment, slot } = openPractice;
  const offset = fragment.getBoundingClientRect().left - slot.getBoundingClientRect().left;
  slot.style.setProperty("--practice-offset", Math.max(0, offset) + "px");
}

function togglePractice(fragment, slot, trigger, active) {
  const originalTop = trigger.getBoundingClientRect().top;
  const wasOpen = openPractice?.fragment === fragment;
  closePractice();
  if (!wasOpen) {
    const panel = buildPractice(active, trigger);
    slot.replaceChildren(panel);
    slot.hidden = false;
    openPractice = { fragment, slot };
    for (const control of fragment.querySelectorAll("button")) {
      control.setAttribute("aria-expanded", "true");
    }
    trigger.setAttribute("aria-expanded", "true");
    alignPractice();
  }
  // 从上方歌词行移走卡片时，补偿布局位移，让当前点击位置留在视口原处。
  const shift = trigger.getBoundingClientRect().top - originalTop;
  if (shift) window.scrollBy({ top: shift, behavior: "instant" });
}

window.addEventListener("resize", alignPractice);

function buildPractice(active, trigger) {
  const panel = node("div", "practice-panel");
  const header = node("div", "section-title");
  const heading = node("h3", "", "一起读读看");
  const close = node("button", "secondary", "关闭");
  close.type = "button";
  close.addEventListener("click", () => {
    closePractice();
    trigger.focus({ preventScroll: true });
  });
  header.append(heading, close);
  panel.append(header);
  for (const annotation of active) {
    const item = node("article", "practice-item");
    const title = node("h4", "", annotation.text);
    title.append(node("span", "category-label " + annotation.category, categories[annotation.category]));
    item.append(title);
    if (annotation.ipa) {
      const ipa = node("p", "ipa-detail");
      const spoken = node("span", "ipa-script");
      spokenContents(spoken, annotation.ipa);
      ipa.append("常规读法 ", node("span", "ipa-script", annotation.ipa.careful), "　口语示范 ", spoken);
      item.append(ipa);
    }
    item.append(node("p", "", annotation.speaking_tip_zh));
    panel.append(item);
  }
  return panel;
}

function openEditor(row, line, number) {
  const existing = find("annotated-lyrics").querySelector(".line-editor");
  if (existing) {
    existing.querySelector("input").focus();
    return;
  }
  if (row.contains(openPractice?.slot)) closePractice();
  const reading = row.querySelector(".reading-line");
  const edit = row.querySelector(".edit-button");
  const form = node("form", "line-editor");
  const controls = node("fieldset", "");
  const input = node("input", "");
  input.value = line.text;
  input.required = true;
  input.maxLength = 12000;
  input.setAttribute("aria-label", "第 " + (number + 1) + " 行歌词");
  const save = node("button", "primary", "保存");
  save.type = "submit";
  const cancel = node("button", "secondary", "取消");
  cancel.type = "button";
  const notice = node("p", "muted");
  notice.setAttribute("role", "status");
  cancel.addEventListener("click", () => {
    form.remove();
    reading.hidden = false;
    edit.hidden = false;
    edit.focus();
  });
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const text = input.value.trim();
    if (!text) {
      notice.textContent = "请输入一行歌词。";
      input.focus();
      return;
    }
    const job = currentJob;
    start(() => postJson("/api/jobs/" + job + "/correct", { line: number, text }),
          "正在更新本行发音…", { preserve: true, editNote: notice, editedLine: number });
  });
  controls.append(input, save, cancel, notice);
  form.append(controls);
  reading.hidden = true;
  edit.hidden = true;
  reading.after(form);
  input.focus();
}

function addTimeline(row, line, number) {
  const times = timeRange(line);
  const interval = line.start_seconds === null ? line.search_window : [line.start_seconds, line.end_seconds];
  if (times && audioFile && interval) {
    const play = node("button", "time time-button", times);
    play.type = "button";
    play.setAttribute("aria-label", "播放第 " + (number + 1) + " 行 " + times);
    play.addEventListener("click", () => playClip(...interval, number));
    row.append(play);
  } else if (times) {
    row.append(node("span", "time", times));
  }
}

function renderLyrics(job) {
  const target = find("annotated-lyrics");
  closePractice();
  target.replaceChildren();
  const annotations = (job.analysis?.annotations || []).map((annotation, index) => ({
    ...annotation,
    // 接口保留 ipa 原值，词下音标与提示只读取同一份版本化展示数据。
    ipa: annotation.ipa_display,
    speaking_tip_zh: annotation.ipa_display_note,
    index,
  }));
  for (const [number, line] of job.lines.entries()) {
    const row = node("div", "lyric-row");
    row.dataset.line = number + 1;
    const reading = node("div", "reading-line");
    addTimeline(row, line, number);
    const characters = Array.from(line.text);
    const relevant = annotations.filter((item) => item.start < line.end && item.end > line.start);
    const practice = node("div", "practice-slot");
    practice.id = "practice-line-" + (number + 1);
    practice.setAttribute("role", "region");
    practice.setAttribute("aria-label", "第 " + (number + 1) + " 行跟读提示");
    practice.hidden = true;

    // 重叠区间共用一个完整词组，避免下面的 IPA 把同一词组拆散、撑开。
    const groups = [];
    for (const item of [...relevant].sort((left, right) => left.start - right.start)) {
      const previous = groups.at(-1);
      if (previous && item.start < previous.end) {
        previous.end = Math.min(line.end, Math.max(previous.end, item.end));
        previous.items.push(item);
      } else {
        groups.push({start: Math.max(line.start, item.start), end: Math.min(line.end, item.end), items: [item]});
      }
    }
    let cursor = line.start;
    for (const group of groups) {
      reading.append(characters.slice(cursor - line.start, group.start - line.start).join(""));
      const phrase = node("span", "lyric-fragment annotation-group");
      const words = node("span", "phrase-text");
      const readings = node("span", "phrase-readings");
      if (group.items.length > 2) readings.classList.add("readings-many");
      const anchors = new Map();
      const edges = new Set([group.start, group.end]);
      for (const item of group.items) {
        edges.add(Math.max(group.start, item.start));
        edges.add(Math.min(group.end, item.end));
      }
      const cuts = [...edges].sort((left, right) => left - right);
      for (let index = 1; index < cuts.length; index += 1) {
        const left = cuts[index - 1];
        const right = cuts[index];
        const content = characters.slice(left - line.start, right - line.start).join("");
        const active = group.items.filter((item) => item.start <= left && item.end >= right);
        if (!active.length || !content.trim()) {
          words.append(content);
          continue;
        }
        const fragment = node("span", "phrase-piece");
        const button = node("button", "highlight " + active[0].category, content);
        button.type = "button";
        button.dataset.annotations = active.map((item) => item.index).join(",");
        if (active.length > 1) {
          button.classList.add("overlap");
          const lines = node("span", "mark-lines");
          lines.setAttribute("aria-hidden", "true");
          for (const category of new Set(active.map((item) => item.category))) {
            lines.append(node("span", "mark-line " + category));
          }
          button.append(lines);
        }
        button.setAttribute("aria-controls", practice.id);
        button.setAttribute("aria-expanded", "false");
        const labels = [...new Set(active.map((item) => categories[item.category]))].join("、");
        button.setAttribute("aria-label", content.trim() + " · " + labels);
        button.addEventListener("click", () => togglePractice(fragment, practice, button, active));
        fragment.append(button);
        words.append(fragment);
        anchors.set(left, {fragment, active});
      }
      for (const item of group.items) {
        if (!item.ipa) {
          readings.append(node("span", "ipa-display-note", "英式读法核对中，可先试听。"));
          continue;
        }
        const anchor = anchors.get(Math.max(group.start, item.start)) || anchors.values().next().value;
        if (!anchor) continue;
        const ipa = node("button", "ipa-below " + item.category);
        ipa.type = "button";
        ipa.dataset.ipaAnnotation = item.index;
        ipa.dataset.annotationStart = item.start;
        ipa.dataset.annotationEnd = item.end;
        ipa.dataset.annotationCategory = item.category;
        ipa.setAttribute("aria-label", item.text + " 的常规读法与口语示范音标 · " + categories[item.category]);
        ipa.setAttribute("aria-controls", practice.id);
        ipa.setAttribute("aria-expanded", "false");
        const spoken = node("span", "ipa-spoken ipa-script");
        spokenContents(spoken, item.ipa);
        const carefulLine = node("span", "ipa-line");
        const spokenLine = node("span", "ipa-line");
        carefulLine.append(node("span", "ipa-label", "常规读法"), node("span", "ipa-careful ipa-script", item.ipa.careful));
        spokenLine.append(node("span", "ipa-label", "口语示范"), spoken);
        if (group.items.length > 1) ipa.append(node("span", "ipa-word", item.text));
        ipa.append(carefulLine, spokenLine);
        ipa.addEventListener("click", () => togglePractice(anchor.fragment, practice, ipa, anchor.active));
        readings.append(ipa);
      }
      phrase.append(words, readings);
      reading.append(phrase);
      cursor = group.end;
    }
    reading.append(characters.slice(cursor - line.start).join(""));
    if (relevant.length) reading.append(practice);
    const edit = node("button", "edit-button", "改词");
    edit.type = "button";
    edit.setAttribute("aria-label", "编辑第 " + (number + 1) + " 行");
    edit.addEventListener("click", () => openEditor(row, line, number));
    row.append(reading, edit);
    target.append(row);
  }
}

function renderJob(job) {
  find("results").hidden = false;
  document.body.classList.add("is-learning");
  find("change-song").hidden = false;
  find("song-title").textContent = audioFile ? audioFile.name.replace(/\.mp3$/i, "") : "我的歌词";
  find("song-player").hidden = !audioFile;
  songDuration = job.audio_duration || 0;
  updatePlayer();
  const analysis = job.analysis;
  const complete = analysis?.status === "success";
  find("transcript-note").hidden = !job.transcript_partial;
  find("result-notice").hidden = complete;
  find("retry-button").hidden = !analysis || complete;
  find("result-message").textContent = analysis?.status === "partial"
    ? "部分跟读提示未完成，歌词和试听已就绪。"
    : "跟读提示暂时未完成，可以继续听歌或重试。";
  renderLyrics(job);
  const lyrics = find("annotated-lyrics");
  const pageCount = new Set([...lyrics.querySelectorAll("[data-annotations]")]
    .flatMap((item) => item.dataset.annotations.split(","))).size;
  const ipaCount = new Set([...lyrics.querySelectorAll("[data-ipa-annotation]")]
    .map((item) => item.dataset.ipaAnnotation)).size;
  return {page_count: pageCount, page_ipa_count: ipaCount};
}

find("upload-form").addEventListener("submit", (event) => event.preventDefault());
find("upload-button").addEventListener("click", () => find("audio").click());
find("change-song").addEventListener("click", () => find("audio").click());
find("audio").addEventListener("change", () => {
  const file = find("audio").files[0];
  if (!file) return;
  if (!/\.mp3$/i.test(file.name) || file.size > 30 * 1024 * 1024) {
    status("请选择不超过 30 MB 的 MP3。", null, true);
    return;
  }
  selectAudio(file);
  document.body.classList.remove("is-learning");
  find("change-song").hidden = true;
  start(() => request("/api/jobs/audio", { method: "POST", headers: { "Content-Type": "audio/mpeg" },
                                          body: file }), "正在上传 " + file.name + "…");
});

find("text-form").addEventListener("submit", (event) => {
  event.preventDefault();
  find("guide").close();
  selectAudio(undefined);
  start(() => postJson("/api/jobs/text", { text: find("lyrics").value }), "正在提交歌词…");
});

find("retry-button").addEventListener("click", () => {
  const job = currentJob;
  start(() => postJson("/api/jobs/" + job + "/retry", {}), "正在重试发音分析…", {
    preserve: true, editNote: find("result-message"),
  });
});

request("/api/config").then((config) => {
  if (config.demo) find("upload-help").textContent = "离线回放模式。可直接输入已有例句查看历史标注。";
}).catch(() => status("无法连接本地服务，请检查网页启动命令。", null, true));


for (const button of document.querySelectorAll("[data-dialog]")) {
  button.addEventListener("click", () => find(button.dataset.dialog).showModal());
}
for (const button of document.querySelectorAll(".dialog-close")) {
  button.addEventListener("click", () => button.closest("dialog").close());
}
