(function () {
  "use strict";

  const ALLOWED = [".wav", ".mp3", ".m4a", ".flac"];

  const dropzone = document.getElementById("dropzone");
  const fileInput = document.getElementById("file-input");
  const fileNameEl = document.getElementById("file-name");
  const asrModel = document.getElementById("asr-model");
  const summarySize = document.getElementById("summary-size");
  const btnSubmit = document.getElementById("btn-submit");
  const btnReset = document.getElementById("btn-reset");
  const formError = document.getElementById("form-error");
  const progressSection = document.getElementById("progress-section");
  const statusLine = document.getElementById("status-line");
  const progressFill = document.getElementById("progress-fill");
  const resultsSection = document.getElementById("results-section");
  const metaLine = document.getElementById("meta-line");
  const outTranscript = document.getElementById("out-transcript");
  const outSummary = document.getElementById("out-summary");
  const btnCopyTranscript = document.getElementById("btn-copy-transcript");
  const btnCopySummary = document.getElementById("btn-copy-summary");

  const steps = {
    upload: document.querySelector('.step[data-stage="upload"]'),
    asr: document.querySelector('.step[data-stage="asr"]'),
    summarize: document.querySelector('.step[data-stage="summarize"]'),
  };

  let selectedFile = null;
  let pollTimer = null;
  let currentJobId = null;

  function extOf(name) {
    const i = name.lastIndexOf(".");
    return i >= 0 ? name.slice(i).toLowerCase() : "";
  }

  function setFile(file) {
    if (!file) {
      selectedFile = null;
      fileNameEl.textContent = "";
      btnSubmit.disabled = true;
      return;
    }
    const ext = extOf(file.name);
    if (!ALLOWED.includes(ext)) {
      showError("Допустимы только файлы: " + ALLOWED.join(", "));
      return;
    }
    hideError();
    selectedFile = file;
    fileNameEl.textContent = file.name;
    btnSubmit.disabled = false;
  }

  function showError(msg) {
    formError.textContent = msg;
    formError.hidden = false;
  }

  function hideError() {
    formError.hidden = true;
    formError.textContent = "";
  }

  function setDropActive(on) {
    dropzone.classList.toggle("dropzone--active", on);
  }

  function stageClass(state) {
    if (state === "done") return "step--done";
    if (state === "processing") return "step--processing";
    if (state === "error") return "step--error";
    return "step--pending";
  }

  function applyStages(st) {
    for (const key of Object.keys(steps)) {
      const el = steps[key];
      if (!el) continue;
      el.classList.remove(
        "step--pending",
        "step--processing",
        "step--done",
        "step--error"
      );
      el.classList.add(stageClass(st[key] || "pending"));
    }
    const pct = progressFromStages(st);
    progressFill.style.width = pct + "%";
    progressFill.parentElement.setAttribute("aria-valuenow", String(pct));
  }

  function progressFromStages(st) {
    const u = st.upload || "pending";
    const a = st.asr || "pending";
    const s = st.summarize || "pending";
    if (u === "error" || a === "error" || s === "error") return 100;
    if (s === "done") return 100;
    if (s === "processing") return 78;
    if (a === "done") return 55;
    if (a === "processing") return 33;
    if (u === "done") return 12;
    return 5;
  }

  function statusRu(status, stages) {
    if (status === "queued") return "В очереди…";
    if (status === "processing") {
      if (stages.asr === "processing") return "Транскрибация…";
      if (stages.summarize === "processing") return "Саммари (Ollama)…";
      return "Обработка…";
    }
    if (status === "done") return "Готово";
    if (status === "error") return "Ошибка";
    return status;
  }

  function stopPoll() {
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  async function fetchJson(url, opts) {
    const r = await fetch(url, opts);
    const text = await r.text();
    let data = null;
    try {
      data = text ? JSON.parse(text) : null;
    } catch {
      data = { detail: text };
    }
    if (!r.ok) {
      const err = new Error(r.statusText);
      err.status = r.status;
      err.data = data;
      throw err;
    }
    return data;
  }

  function formatDetail(data) {
    if (data == null) return "";
    if (typeof data.detail === "string") return data.detail;
    if (data.detail && typeof data.detail === "object") {
      return JSON.stringify(data.detail, null, 2);
    }
    return JSON.stringify(data, null, 2);
  }

  async function pollOnce() {
    if (!currentJobId) return;
    try {
      const job = await fetchJson("/jobs/" + encodeURIComponent(currentJobId));
      statusLine.textContent = statusRu(job.status, job.stages);
      applyStages(job.stages || {});

      if (job.status === "done") {
        stopPoll();
        btnSubmit.disabled = false;
        await loadResult();
        return;
      }
      if (job.status === "error") {
        stopPoll();
        btnSubmit.disabled = false;
        showError(job.error || "Неизвестная ошибка");
        applyStages(job.stages || {});
        return;
      }
    } catch (e) {
      stopPoll();
      btnSubmit.disabled = false;
      showError(
        e.data ? formatDetail(e.data) : e.message || String(e)
      );
    }
  }

  async function loadResult() {
    try {
      const res = await fetchJson(
        "/jobs/" + encodeURIComponent(currentJobId) + "/result"
      );
      outTranscript.textContent = res.transcript || "";
      outSummary.textContent = res.summary || "";
      const t = res.timings || {};
      const m = res.model_info || {};
      const parts = [];
      if (t.asr_ms != null) parts.push("ASR: " + t.asr_ms + " ms");
      if (t.summarize_ms != null) parts.push("LLM: " + t.summarize_ms + " ms");
      if (m.whisper_model) parts.push("Whisper: " + m.whisper_model);
      if (m.ollama_model) parts.push("Ollama: " + m.ollama_model);
      if (m.summary_mode) parts.push("Режим саммари: " + m.summary_mode);
      metaLine.textContent = parts.join(" · ");
      resultsSection.hidden = false;
    } catch (e) {
      showError(
        e.data ? formatDetail(e.data) : e.message || String(e)
      );
    }
  }

  async function submitJob() {
    hideError();
    if (!selectedFile) return;
    btnSubmit.disabled = true;
    resultsSection.hidden = true;
    outTranscript.textContent = "";
    outSummary.textContent = "";
    progressSection.hidden = false;
    btnReset.hidden = false;
    applyStages({ upload: "done", asr: "pending", summarize: "pending" });
    statusLine.textContent = "Отправка…";

    const fd = new FormData();
    fd.append("asr_model", asrModel.value);
    fd.append("summary_size", summarySize.value);
    fd.append("audio_file", selectedFile, selectedFile.name);

    try {
      const created = await fetchJson("/jobs", { method: "POST", body: fd });
      currentJobId = created.job_id;
      statusLine.textContent = "В очереди…";
      applyStages({ upload: "done", asr: "pending", summarize: "pending" });
      stopPoll();
      pollTimer = setInterval(pollOnce, 900);
      pollOnce();
    } catch (e) {
      btnSubmit.disabled = false;
      progressSection.hidden = true;
      showError(
        e.status === 413
          ? "Файл слишком большой"
          : e.data
            ? formatDetail(e.data)
            : e.message || String(e)
      );
    }
  }

  function resetUi() {
    stopPoll();
    currentJobId = null;
    selectedFile = null;
    fileInput.value = "";
    fileNameEl.textContent = "";
    hideError();
    progressSection.hidden = true;
    resultsSection.hidden = true;
    btnReset.hidden = true;
    btnSubmit.disabled = true;
    progressFill.style.width = "0%";
    applyStages({ upload: "pending", asr: "pending", summarize: "pending" });
  }

  async function copyText(text, btn) {
    try {
      await navigator.clipboard.writeText(text);
      const prev = btn.textContent;
      btn.textContent = "Скопировано";
      setTimeout(function () {
        btn.textContent = prev;
      }, 1600);
    } catch {
      showError("Не удалось скопировать в буфер обмена");
    }
  }

  dropzone.addEventListener("click", function () {
    fileInput.click();
  });

  dropzone.addEventListener("keydown", function (e) {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      fileInput.click();
    }
  });

  fileInput.addEventListener("change", function () {
    const f = fileInput.files && fileInput.files[0];
    setFile(f || null);
  });

  ["dragenter", "dragover"].forEach(function (ev) {
    dropzone.addEventListener(ev, function (e) {
      e.preventDefault();
      e.stopPropagation();
      setDropActive(true);
    });
  });

  ["dragleave", "drop"].forEach(function (ev) {
    dropzone.addEventListener(ev, function (e) {
      e.preventDefault();
      e.stopPropagation();
      setDropActive(false);
    });
  });

  dropzone.addEventListener("drop", function (e) {
    const dt = e.dataTransfer;
    if (!dt || !dt.files || !dt.files.length) return;
    setFile(dt.files[0]);
    fileInput.value = "";
  });

  btnSubmit.addEventListener("click", submitJob);
  btnReset.addEventListener("click", resetUi);

  btnCopyTranscript.addEventListener("click", function () {
    copyText(outTranscript.textContent, btnCopyTranscript);
  });
  btnCopySummary.addEventListener("click", function () {
    copyText(outSummary.textContent, btnCopySummary);
  });
})();
