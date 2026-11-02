"use strict";

const assert = require("node:assert/strict");
const { webcrypto } = require("node:crypto");
const filesystem = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const virtualMachine = require("node:vm");

/** 실제 서비스나 브라우저 없이 제어 요청과 저장 순서를 검사할 환경을 만듭니다. */
function createBrowserHarness(storage = new Map()) {
  const sourcePath = path.resolve(__dirname, "../../web/ManagementServer/application.js");
  const source = filesystem.readFileSync(sourcePath, "utf8").replace(/initializeApplication\(\);\s*$/, "");
  const context = virtualMachine.createContext({
    crypto: webcrypto,
    document: { querySelectorAll: () => [] },
    localStorage: {
      getItem: (key) => storage.get(key) || null,
      setItem: (key, value) => storage.set(key, value),
    },
  });
  virtualMachine.runInContext(source + `
    globalThis.testApplication = {
      state, controlService, restorePendingOperations, reconcileOperations,
      pendingOperationStorageKey,
    };
  `, context);
  const application = context.testApplication;
  application.state.snapshot = { operations: [], comfy: { running: [], pending: [] } };
  const renderedOperations = [];
  context.renderOperations = (operations) => {
    renderedOperations.push(JSON.parse(JSON.stringify(application.reconcileOperations(operations))));
  };
  context.renderButtons = () => {};
  context.refreshStatus = async () => {};
  context.showToast = () => {};
  return { context, application, storage, renderedOperations };
}

test("실행 profile 선택을 취소하면 접수와 브라우저 기록을 만들지 않습니다", async () => {
  const harness = createBrowserHarness();
  harness.application.state.snapshot.llm = { profiles: [] };
  harness.context.selectExecutionProfile = async () => null;
  harness.context.requestApi = () => assert.fail("취소 후 요청하면 안 됩니다.");
  await harness.application.controlService({ currentTarget: { dataset: { target: "llm", action: "start" } } });
  assert.equal(harness.application.state.pendingOperations.length, 0);
  assert.equal(harness.application.state.actionPending, false);
});

test("선택한 profile과 revision을 동일한 기동 요청에 고정합니다", async () => {
  const harness = createBrowserHarness();
  harness.application.state.snapshot.llm = { profiles: [] };
  harness.context.selectExecutionProfile = async () => ({ identifier: "polystrata-qwen36", revision: "selected-revision" });
  let requestedOperation;
  harness.context.requestApi = async (requestPath, options) => {
    if (requestPath === "/api/operations") return [requestedOperation];
    const request = JSON.parse(options.body);
    assert.equal(request.profile_id, "polystrata-qwen36");
    assert.equal(request.configuration_revision, "selected-revision");
    requestedOperation = { ...request, target: "llm", action: "start", status: "queued", created_at: 1 };
    return requestedOperation;
  };
  await harness.application.controlService({ currentTarget: { dataset: { target: "llm", action: "start" } } });
});

test("버튼 요청은 응답 전에 저장·표시되고 동일 요청의 서버 상태로 갱신됩니다", async () => {
  const harness = createBrowserHarness();
  let acceptRequest;
  let requestedIdentifier;
  harness.context.requestApi = (requestPath, options) => {
    if (requestPath === "/api/operations") {
      return Promise.resolve([{ identifier: requestedIdentifier, target: "llm", action: "start", status: "running", created_at: 1 }]);
    }
    requestedIdentifier = JSON.parse(options.body).identifier;
    const storedOperations = JSON.parse(harness.storage.get(harness.application.pendingOperationStorageKey));
    assert.equal(storedOperations[0].identifier, requestedIdentifier);
    assert.equal(storedOperations[0].status, "submitting");
    assert.equal(harness.renderedOperations[0][0].status, "submitting");
    return new Promise((resolve) => { acceptRequest = resolve; });
  };
  const request = harness.application.controlService({ currentTarget: { dataset: { target: "llm", action: "start" } } });
  assert.equal(harness.application.state.actionPending, true);
  acceptRequest({ identifier: requestedIdentifier, target: "llm", action: "start", status: "queued", created_at: 1 });
  await request;
  assert.equal(harness.renderedOperations.at(-1)[0].status, "running");
  assert.equal(harness.application.state.pendingOperations.length, 0);
  assert.equal(harness.application.state.actionPending, false);
});

test("응답을 잃고 브라우저가 재시작해도 요청을 보존하며 자동 재전송하지 않습니다", async () => {
  const harness = createBrowserHarness();
  harness.context.requestApi = async () => { throw new Error("connection lost"); };
  await harness.application.controlService({ currentTarget: { dataset: { target: "llm", action: "start" } } });
  const restoredHarness = createBrowserHarness(harness.storage);
  restoredHarness.context.requestApi = () => { assert.fail("자동 재전송하면 안 됩니다."); };
  restoredHarness.application.restorePendingOperations();
  const pendingOperation = restoredHarness.application.state.pendingOperations[0];
  assert.equal(pendingOperation.status, "unconfirmed");
  const operations = restoredHarness.application.reconcileOperations([{ ...pendingOperation, status: "interrupted" }]);
  assert.equal(operations.length, 1);
  assert.equal(operations[0].status, "interrupted");
  assert.equal(restoredHarness.application.state.pendingOperations.length, 0);
});

test("클릭 기록을 저장하지 못하면 서비스 제어를 전송하지 않습니다", async () => {
  const harness = createBrowserHarness();
  harness.context.localStorage.setItem = () => { throw new Error("storage unavailable"); };
  harness.context.requestApi = () => { assert.fail("기록 없이 서비스를 실행하면 안 됩니다."); };
  await harness.application.controlService({ currentTarget: { dataset: { target: "llm", action: "start" } } });
  assert.equal(harness.renderedOperations.at(-1)[0].status, "failed");
  assert.match(harness.renderedOperations.at(-1)[0].message, /제어를 시작하지 않았습니다/);
});

test("서버에서 명확히 거부한 요청은 실패 상태로 갱신됩니다", async () => {
  const harness = createBrowserHarness();
  harness.context.requestApi = async () => {
    const error = new Error("다른 제어 작업이 진행 중입니다.");
    error.httpStatus = 409;
    throw error;
  };
  await harness.application.controlService({ currentTarget: { dataset: { target: "llm", action: "start" } } });
  assert.equal(harness.renderedOperations.at(-1)[0].status, "failed");
  assert.match(harness.renderedOperations.at(-1)[0].message, /제어 요청이 거부됐습니다/);
  const restoredHarness = createBrowserHarness(harness.storage);
  restoredHarness.application.restorePendingOperations();
  assert.equal(restoredHarness.application.state.pendingOperations[0].status, "failed");
});
