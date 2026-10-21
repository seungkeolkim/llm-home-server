"use strict";

const elements = Object.fromEntries(
  [...document.querySelectorAll("[id]")].map((element) => [
    element.id,
    element,
  ]),
);
const state = {
  csrf: null,
  revision: null,
  snapshot: null,
  polling: false,
  actionPending: false,
  queueSignature: null,
  operationSignature: null,
};
const statusLabels = {
  ready: "준비 완료",
  starting: "기동 중",
  stopping: "종료 중",
  stopped: "중지",
  generating: "생성 중",
  unloaded: "모델 미로드",
  unavailable: "연결 확인 필요",
  running: "실행 중",
  queued: "대기 중",
  accepted: "요청 접수",
  succeeded: "완료",
  failed: "실패",
};

/** 서버 API를 호출하고 인증 만료와 오류 메시지를 구분합니다. */
async function requestApi(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-Token": state.csrf || "",
      ...options.headers,
    },
    cache: "no-store",
  });
  const document = await response.json();
  if (!response.ok) {
    if (response.status === 401 && path !== "/api/access") showAccessScreen();
    const message =
      typeof document.detail === "string"
        ? document.detail
        : "요청 내용을 확인해 주세요.";
    throw new Error(message);
  }
  return document;
}

/** 텍스트가 바뀔 때만 DOM을 갱신해 모바일 화면의 위치를 유지합니다. */
function setText(identifier, value) {
  if (elements[identifier].textContent !== String(value))
    elements[identifier].textContent = value;
}

/** 상태 배지의 색상과 설명을 함께 갱신합니다. */
function updateBadge(identifier, status, label) {
  const element = elements[identifier];
  element.textContent = label || statusLabels[status] || status;
  const category = ["ready", "succeeded", "accepted"].includes(status)
    ? "ready"
    : ["generating", "queued", "running", "starting", "stopping"].includes(status)
      ? "busy"
      : ["failed", "unavailable"].includes(status)
        ? "error"
        : "stopped";
  element.className = `badge ${category}`;
}

/** 숫자의 읽기 쉬운 GiB 표기를 만듭니다. */
function gibibytes(byteCount) {
  return (byteCount / 1024 ** 3).toFixed(1);
}

/** 리소스 수치와 progress만 갱신합니다. */
function renderResources(resources) {
  const memory = resources.ram;
  elements["ram-free"].innerHTML =
    `${gibibytes(memory.available_bytes)}<small> GiB 여유</small>`;
  setText("ram-percent", `${memory.percent.toFixed(0)}% 사용`);
  setText(
    "ram-detail",
    `${gibibytes(memory.used_bytes)} / ${gibibytes(memory.total_bytes)} GiB 사용`,
  );
  elements["ram-progress"].value = memory.percent;
  setText("cpu-percent", `${resources.cpu_percent.toFixed(0)}%`);
  elements["cpu-progress"].value = resources.cpu_percent;
  const gpu = resources.gpus[0];
  if (gpu) {
    const usedPercent = (gpu.used_mib / gpu.total_mib) * 100;
    elements["vram-free"].innerHTML =
      `${((gpu.total_mib - gpu.used_mib) / 1024).toFixed(1)}<small> GiB 여유</small>`;
    setText("vram-percent", `${usedPercent.toFixed(0)}% 사용`);
    setText("gpu-name", gpu.name);
    setText("gpu-percent", `${gpu.utilization_percent.toFixed(0)}%`);
    setText("gpu-temperature", `${gpu.temperature_c.toFixed(0)} °C`);
    setText("gpu-power", `${gpu.power_w} W · 연산 사용률`);
    elements["vram-progress"].value = usedPercent;
    elements["gpu-progress"].value = gpu.utilization_percent;
  } else {
    setText("vram-free", "확인 불가");
    setText("gpu-percent", "—");
    setText("gpu-temperature", "—");
    setText("gpu-name", resources.gpu_error || "GPU 정보 없음");
    elements["vram-progress"].value = 0;
    elements["gpu-progress"].value = 0;
  }
}

/** 상태 조회에서 받은 문자열을 HTML 해석 없이 새 요소로 만듭니다. */
function textElement(tagName, className, text) {
  const element = document.createElement(tagName);
  element.className = className;
  element.textContent = text;
  return element;
}

/** 실제 ComfyUI queue만 표시하며 취소 버튼을 만들지 않습니다. */
function renderQueue(queue) {
  updateBadge(
    "comfy-state",
    queue.connected ? "ready" : "unavailable",
    queue.connected ? "연결됨" : "연결 안 됨",
  );
  setText("running-count", queue.connected ? queue.running.length : "—");
  setText("pending-count", queue.connected ? queue.pending.length : "—");
  const signature = JSON.stringify(queue);
  if (signature === state.queueSignature) return;
  state.queueSignature = signature;
  const fragment = document.createDocumentFragment();
  for (const [queueName, queueLabel] of [
    ["running", "실행 중"],
    ["pending", "대기 중"],
  ]) {
    for (const item of queue[queueName]) {
      const row = textElement("div", "queue-item", "");
      row.append(
        textElement("span", "badge", queueLabel),
        textElement("code", "", item.identifier),
      );
      fragment.append(row);
    }
  }
  if (!fragment.childNodes.length) {
    fragment.append(
      textElement(
        "p",
        "empty-state",
        queue.connected
          ? "실행 중이거나 대기 중인 작업이 없습니다."
          : queue.error,
      ),
    );
  }
  elements["queue-list"].replaceChildren(fragment);
}

/** 접수와 실제 완료를 구분해 제어 이력을 표시합니다. */
function renderOperations(operations) {
  const signature = JSON.stringify(operations);
  if (signature === state.operationSignature) return;
  state.operationSignature = signature;
  const fragment = document.createDocumentFragment();
  for (const operation of operations) {
    const row = textElement("article", "operation-row", "");
    const time = textElement(
      "time",
      "",
      new Date(operation.created_at * 1000).toLocaleString("ko-KR", {
        month: "numeric",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      }),
    );
    const detail = textElement("div", "", "");
    const target = {
      llm: "LLM 서버",
      librechat: "LibreChat stack",
      comfy: "ComfyUI",
    }[operation.target];
    const action = { start: "기동", stop: "종료", unload: "모델·cache unload" }[
      operation.action
    ];
    detail.append(textElement("strong", "", `${target} · ${action}`));
    detail.append(
      textElement(
        "p",
        "",
        operation.message || "처리 중입니다. 잠시 기다려 주세요.",
      ),
    );
    const badge = textElement(
      "span",
      "badge",
      statusLabels[operation.status] || operation.status,
    );
    badge.classList.add(
      ["failed"].includes(operation.status)
        ? "error"
        : ["queued", "running"].includes(operation.status)
          ? "busy"
          : "ready",
    );
    row.append(time, detail, badge);
    fragment.append(row);
  }
  if (!operations.length)
    fragment.append(textElement("p", "muted", "아직 제어 이력이 없습니다."));
  elements["operation-list"].replaceChildren(fragment);
}

/** 현재 접속한 LAN·외부 hostname을 그대로 사용해 각 서버로 연결합니다. */
function renderLinks(links, externalLinks) {
  const browserHostname = window.location.hostname;
  const localHostname =
    browserHostname === "localhost" ||
    browserHostname === "127.0.0.1" ||
    browserHostname === "::1" ||
    browserHostname.startsWith("192.168.") ||
    browserHostname.startsWith("10.") ||
    /^172\.(1[6-9]|2\d|3[01])\./.test(browserHostname);
  for (const [identifier, target] of [
    ["chat-shortcut", "librechat"],
    ["llm-shortcut", "llm"],
    ["comfy-shortcut", "comfy_home"],
  ]) {
    const destination = new URL(window.location.href);
    destination.port = String(
      (localHostname ? links : externalLinks || links)[target],
    );
    destination.pathname = "/";
    destination.hash = "";
    destination.search = "";
    elements[identifier].href = destination.href;
  }
}

/** 현재 서비스 상태와 진행 중 작업을 기준으로 버튼 중복 실행을 방지합니다. */
function renderButtons(snapshot) {
  const busy =
    state.actionPending ||
    snapshot.operations.some((operation) =>
      ["queued", "running"].includes(operation.status),
    );
  for (const button of document.querySelectorAll("[data-target]")) {
    let disabled = busy;
    if (button.dataset.target === "comfy")
      disabled ||= !snapshot.comfy.connected;
    if (button.dataset.target === "llm") {
      if (button.dataset.action === "start")
        disabled ||= ["ready", "generating"].includes(snapshot.llm.state);
      if (button.dataset.action === "stop")
        disabled ||= snapshot.llm.state === "stopped";
    }
    if (button.dataset.target === "librechat") {
      disabled ||= !snapshot.librechat.engine_available;
      const services = Object.values(snapshot.librechat.services);
      if (button.dataset.action === "start")
        disabled ||=
          services.length === 2 &&
          services.every(
            (service) =>
              service.state === "running" && service.health === "healthy",
          );
      if (button.dataset.action === "stop")
        disabled ||=
          services.length === 2 &&
          services.every((service) =>
            ["stopped", "exited"].includes(service.state),
          );
    }
    button.disabled = disabled;
  }
}

/** 완성된 snapshot을 각 화면 영역에 반영합니다. */
function renderSnapshot(snapshot) {
  state.snapshot = snapshot;
  renderResources(snapshot.resources);
  const llmOperation = snapshot.operations.find(
    (operation) =>
      operation.target === "llm" &&
      ["queued", "running"].includes(operation.status),
  );
  updateBadge(
    "llm-state",
    llmOperation
      ? llmOperation.action === "start"
        ? "starting"
        : "stopping"
      : snapshot.llm.state,
  );
  setText("llm-engine", snapshot.llm.name);
  setText("llm-model", snapshot.llm.model);
  setText(
    "llm-description",
    snapshot.llm.in_flight
      ? `현재 ${snapshot.llm.in_flight}개 요청을 처리 중입니다.`
      : `API :${snapshot.llm.port} · 현재 설정된 모델을 실행합니다.`,
  );
  for (const serviceName of ["librechat", "mongodb"]) {
    const service = snapshot.librechat.services[serviceName];
    setText(
      `${serviceName}-health`,
      service
        ? service.health === "healthy"
          ? "정상"
          : service.state === "running"
            ? "준비 중"
            : "중지"
        : "확인 불가",
    );
  }
  const containers = Object.values(snapshot.librechat.services);
  const stackState = !snapshot.librechat.engine_available
    ? "unavailable"
    : containers.every(
          (service) =>
            service.state === "running" && service.health === "healthy",
        )
      ? "ready"
      : containers.some((service) => service.state === "running")
        ? "running"
        : "stopped";
  updateBadge(
    "librechat-state",
    stackState,
    !snapshot.librechat.engine_available ? "Docker 연결 안 됨" : undefined,
  );
  renderQueue(snapshot.comfy);
  renderOperations(snapshot.operations);
  renderLinks(snapshot.links, snapshot.external_links);
  renderButtons(snapshot);
  setText(
    "updated-at",
    `${new Date(snapshot.at * 1000).toLocaleTimeString("ko-KR")} 기준 · 3초 간격`,
  );
}

/** 접속 화면을 표시하고 메모리에 보관한 화면 상태를 잠급니다. */
function showAccessScreen() {
  state.csrf = null;
  elements.application.classList.add("hidden");
  elements["access-screen"].classList.remove("hidden");
}

/** 허용한 브라우저 세션으로 관리 화면을 엽니다. */
function showApplication(session) {
  state.csrf = session.csrf;
  state.revision = session.asset_revision;
  elements["access-screen"].classList.add("hidden");
  elements.application.classList.remove("hidden");
  elements["access-string"].value = "";
}

/** 오류와 작업 접수를 화면 하단에 일시 표시합니다. */
function showToast(message) {
  elements.toast.textContent = message;
  elements.toast.classList.remove("hidden");
  clearTimeout(state.toastTimer);
  state.toastTimer = setTimeout(
    () => elements.toast.classList.add("hidden"),
    5000,
  );
}

/** 데이터 갱신 요청이 겹치지 않도록 순차 실행합니다. */
async function refreshStatus() {
  if (!state.csrf || state.polling || document.hidden) return;
  state.polling = true;
  try {
    const snapshot = await requestApi("/api/status");
    if (snapshot.asset_revision !== state.revision && !state.actionPending) {
      window.location.reload();
      return;
    }
    if (!snapshot.ready)
      throw new Error(snapshot.error || "첫 상태를 수집하고 있습니다.");
    renderSnapshot(snapshot);
    updateBadge("connection-status", "ready", "연결됨");
    elements["connection-error"].classList.add("hidden");
  } catch (error) {
    updateBadge("connection-status", "unavailable", "연결 확인 중");
    elements["connection-error"].textContent = error.message;
    elements["connection-error"].classList.remove("hidden");
    for (const button of document.querySelectorAll("[data-target]"))
      button.disabled = true;
  } finally {
    state.polling = false;
  }
}

/** 종료·메모리 해제 같은 명시적인 사용자 조작을 확인받습니다. */
function confirmAction(title, message) {
  elements["confirm-title"].textContent = title;
  elements["confirm-message"].textContent = message;
  elements["confirm-dialog"].returnValue = "cancel";
  elements["confirm-dialog"].showModal();
  return new Promise((resolve) =>
    elements["confirm-dialog"].addEventListener(
      "close",
      () => resolve(elements["confirm-dialog"].returnValue === "confirm"),
      { once: true },
    ),
  );
}

/** 고정된 서비스 조작을 접수하고 별도 worker의 진행을 표시합니다. */
async function controlService(event) {
  const { target, action } = event.currentTarget.dataset;
  if (state.actionPending) return;
  let message =
    action === "stop"
      ? "서비스를 종료합니다. 현재 작업이 있으면 종료 처리에 시간이 걸릴 수 있습니다."
      : "";
  if (target === "comfy")
    message =
      "ComfyUI 모델과 cache를 비웁니다. 작업은 취소하지 않으며 실행 중인 작업 처리 후 반영됩니다.";
  if (
    target === "llm" &&
    action === "start" &&
    state.snapshot.comfy.running.length + state.snapshot.comfy.pending.length >
      0
  )
    message =
      "ComfyUI queue가 남아 있습니다. LLM 기동 시 RAM·VRAM을 함께 사용합니다. 현재 리소스를 확인하고 진행해 주세요.";
  if (message && !(await confirmAction("서비스 제어", message))) return;
  state.actionPending = true;
  renderButtons(state.snapshot);
  try {
    await requestApi(`/api/services/${target}/${action}`, { method: "POST" });
    showToast(
      "제어 요청을 접수했습니다. 최근 제어 이력에서 진행 상황을 확인하세요.",
    );
    const operations = await requestApi("/api/operations");
    state.snapshot.operations = operations;
    renderOperations(operations);
  } catch (error) {
    showToast(error.message);
  } finally {
    state.actionPending = false;
    renderButtons(state.snapshot);
    await refreshStatus();
  }
}

/** 선택한 제한된 로그만 가져와 dialog에 표시합니다. */
async function openLog(event) {
  try {
    const result = await requestApi(
      `/api/logs/${event.currentTarget.dataset.log}`,
    );
    elements["log-text"].textContent = result.text;
    elements["log-dialog"].showModal();
  } catch (error) {
    showToast(error.message);
  }
}

/** 접속 문자열을 확인하고 화면을 표시합니다. */
async function submitAccess(event) {
  event.preventDefault();
  const button = event.currentTarget.querySelector("button");
  button.disabled = true;
  try {
    const session = await requestApi("/api/access", {
      method: "POST",
      body: JSON.stringify({ access_string: elements["access-string"].value }),
    });
    showApplication(session);
    setText("access-error", "");
    await refreshStatus();
  } catch (error) {
    setText("access-error", error.message);
  } finally {
    button.disabled = false;
  }
}

/** 현재 브라우저의 session을 종료합니다. */
async function lockSession() {
  try {
    await requestApi("/api/lock", { method: "POST" });
    showAccessScreen();
  } catch (error) {
    showToast(error.message);
  }
}

/** 이벤트를 한 번 등록하고 기존 session을 복구합니다. */
async function initializeApplication() {
  elements["access-form"].addEventListener("submit", submitAccess);
  elements["lock-button"].addEventListener("click", lockSession);
  elements["refresh-button"].addEventListener("click", refreshStatus);
  elements["close-log"].addEventListener("click", () =>
    elements["log-dialog"].close(),
  );
  for (const button of document.querySelectorAll("[data-target]"))
    button.addEventListener("click", controlService);
  for (const button of document.querySelectorAll("[data-log]"))
    button.addEventListener("click", openLog);
  document.addEventListener("visibilitychange", refreshStatus);
  try {
    const session = await requestApi("/api/session");
    if (session.allowed) {
      showApplication(session);
      await refreshStatus();
    }
  } catch (error) {
    setText("access-error", error.message);
  }
  setInterval(refreshStatus, 3000);
}

initializeApplication();
