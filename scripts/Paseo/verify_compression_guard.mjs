/** 운영 Session을 변경하지 않고 압축 보호의 범위·실패 예산·오류 축약을 검증합니다. */
import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createJiti } from "../../data/PiCodingAgent/npm/node_modules/jiti/lib/jiti.mjs";

const workspaceDirectory = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const moduleLoader = createJiti(import.meta.url);
const { createCompressionGuard, readCompressionRanges, readRecommendedRanges, registerCompressionGuard } =
    await moduleLoader.import(path.join(workspaceDirectory, "scripts/Paseo/compression-guard.ts"));
const report = { aborts: 0, stops: [] };
const context = { abort: () => { report.aborts += 1; } };
const guard = createCompressionGuard(message => report.stops.push(message));
let nextCallNumber = 0;
const statusText = "Nudge: ACTIVE\n\nCompressible ranges (2, oldest first):\n" +
    "  m00001–m00010  10 msgs  4K\n  m00020–m00030  11 msgs  4K\n\n" +
    "UNCOVERED HISTORY: m00011–m00019 (not recommended)\n";

/** Tool 결과를 만들되 호출마다 다른 id로 중복 방지와 실패 누적을 구분합니다. */
function toolResult(toolName, text, details = {}, isError = false) {
    nextCallNumber += 1;
    return { toolName, toolCallId: `fixture-${nextCallNumber}`, content: [{ type: "text", text }], details, isError };
}

/** 실제 acp_status 형식으로 추천 목록만 갱신합니다. */
function refreshRecommendations() {
    guard.handleToolResult(toolResult("acp_status", statusText), context);
}

/** 실행 전 검사에 전달할 compress 호출을 만듭니다. */
function compressionCall(content) {
    return { toolName: "compress", toolCallId: `call-${nextCallNumber}`, input: { content } };
}

assert.deepEqual(readRecommendedRanges(statusText), [{ start: 1, end: 10 }, { start: 20, end: 30 }]);
assert.equal(readRecommendedRanges("status is unavailable"), undefined);
assert.deepEqual(readRecommendedRanges("Compressible ranges (0, oldest first):\n\nOTHER"), []);
assert.deepEqual(readCompressionRanges('[{"startId":"m00001","endId":"m00010","summary":"summary"}]'),
    [{ start: 1, end: 10 }]);
assert.deepEqual(readCompressionRanges("m00010–m00001\nsummary"), []);
assert.deepEqual(readCompressionRanges('["not an object"]'), []);

const firstFailure = toolResult("compress", "Compression REFUSED (compress.requireNudge)",
    { outcome: "refused", blocksCreated: 0 }, true);
const firstResult = guard.handleToolResult(firstFailure, context);
assert.match(firstResult.content[0].text, /WITHOUT compress/);
assert.equal(guard.handleToolResult(firstFailure, context), undefined);
assert.equal(guard.handleToolCall(compressionCall("m00001–m00010\nsummary")).block, true);
refreshRecommendations();
assert.equal(guard.handleToolCall(compressionCall("m00002–m00009\nsummary")), undefined);
assert.equal(guard.handleToolCall(compressionCall("m00001–m00030\nsummary")).block, true);
guard.handleToolResult(toolResult("bash", "unrelated success"), context);
guard.handleToolResult(toolResult("compress", "out of recommendation", { outcome: "refused", blocksCreated: 0 }, true), context);
refreshRecommendations();
const malformedResult = guard.handleToolResult(toolResult("compress",
    "Invalid arguments for tool compress: Unterminated string\nReceived arguments:\n" + "x".repeat(30000), {}, true), context);
assert.equal(malformedResult.details.compressionGuard.failureCount, 3);
assert.equal(malformedResult.details.compressionGuard.stopped, true);
assert.ok(malformedResult.content[0].text.length < 1000);
assert.doesNotMatch(malformedResult.content[0].text, /Received arguments:/);
assert.equal(report.aborts, 1);
assert.equal(report.stops.length, 1);
assert.equal(guard.handleToolCall({ toolName: "write", input: {} }).terminate, true);

guard.reset();
for (let failureNumber = 0; failureNumber < 2; failureNumber += 1) {
    guard.handleToolResult(toolResult("compress", "refused", { outcome: "refused" }, true), context);
}
guard.handleToolResult(toolResult("compress", "folded", { outcome: "applied", blocksCreated: 1 }), context);
const afterSuccess = guard.handleToolResult(toolResult("compress", "refused", { outcome: "refused" }, true), context);
assert.equal(afterSuccess.details.compressionGuard.failureCount, 1);
assert.equal(report.aborts, 1);
guard.reset();
refreshRecommendations();
assert.equal(guard.handleToolCall(compressionCall("m00031–m00040\nrecent history")).block, true);
guard.reset();
guard.handleToolResult(toolResult("compress", "refused", { outcome: "refused" }, true), context);
guard.handleToolResult(toolResult("acp_status", "failed", {}, true), context);
assert.equal(guard.handleToolCall(compressionCall("m00001–m00010\nsummary")).block, true);

const handlers = new Map();
registerCompressionGuard({ on: (event, handler) => handlers.set(event, handler), sendMessage: () => {} });
const handlerContext = { ...context, ui: { notify: () => {} } };
const startResult = handlers.get("before_agent_start")({ systemPrompt: "original prompt", messageType: "user" });
assert.match(startResult.systemPrompt, /^original prompt/);
const invalidMessage = { role: "toolResult", ...toolResult("compress", "Invalid JSON", {}, true) };
const replacement = handlers.get("message_end")({ message: invalidMessage }, handlerContext);
assert.equal(replacement.message.details.compressionGuard.failureCount, 1);
assert.equal(handlers.get("message_end")({ message: invalidMessage }, handlerContext), undefined);
handlers.get("before_agent_start")({ systemPrompt: "custom event", messageType: "custom" });
const customFailure = handlers.get("tool_result")(toolResult("compress", "refused", {}, true), handlerContext);
assert.equal(customFailure.details.compressionGuard.failureCount, 2);
handlers.get("before_agent_start")({ systemPrompt: "new user request", messageType: "user" });
const nextFailure = handlers.get("tool_result")(toolResult("compress", "refused", {}, true), handlerContext);
assert.equal(nextFailure.details.compressionGuard.failureCount, 1);
guard.reset();
guard.handleToolResult(toolResult("compress", "refused", {}, true), context);
guard.handleToolResult(toolResult("compress", "partial fold", { outcome: "partial", blocksCreated: 1 }, true), context);
const afterPartialFold = guard.handleToolResult(toolResult("compress", "refused", {}, true), context);
assert.equal(afterPartialFold.details.compressionGuard.failureCount, 1);

const summary = { failureLimit: 3, unrelatedSuccessDoesNotReset: true, successfulFoldResets: true,
    duplicateEventsCountOnce: true, newUserRequestResets: true, statusRefreshRequired: true,
    protectedRangesRejected: true, uncoveredHistoryExcluded: true, malformedJsonFallback: true,
    largeArgumentEchoRemoved: true, stoppedRunBlocksAllTools: true, customRunDoesNotReset: true,
    partialFoldResets: true };
await fs.writeFile(path.join(workspaceDirectory, "runtime/Paseo/verification/compression-guard-unit.json"),
    JSON.stringify(summary, null, 2));
console.log(JSON.stringify(summary));
