import type {
    ExtensionAPI, ExtensionContext, ToolCallEvent, ToolResultEvent,
} from "@earendil-works/pi-coding-agent";

export const COMPRESSION_FAILURE_LIMIT = 3;
const MAXIMUM_FAILURE_TEXT_LENGTH = 2400;

type MessageRange = { start: number; end: number };
type CompressionResult = Pick<ToolResultEvent, "toolName" | "toolCallId" | "content" | "details" | "isError">;

export const COMPRESSION_INSTRUCTIONS = [
    "Paseo compression policy:",
    "Only call compress when billion-context has delivered a compression nudge for this model round.",
    "An acp_status report does not grant compression permission. After a requireNudge refusal, continue the task without compressing until a new nudge arrives.",
    "After any compress failure, call acp_status before trying again. Use only the latest listed Compressible ranges; never extend them into protected recent history.",
    "Send one small range per call as a content STRING: a real mNNNNN–mNNNNN header, a real newline, then a concise summary. Do not JSON-encode a plain summary or use literal escaped newlines.",
    `Do not repeat rejected calls. ${COMPRESSION_FAILURE_LIMIT} compression failures without a successful fold stop this user request, even if other tools succeeded between failures.`,
].join("\n");

/** mNNNNN 형식의 ref를 순서 비교용 정수로 읽습니다. */
function readMessageReference(reference: unknown): number | undefined {
    if (typeof reference !== "string" || !/^m\d+$/.test(reference)) return;
    const referenceNumber = Number(reference.slice(1));
    if (Number.isSafeInteger(referenceNumber) && referenceNumber > 0) return referenceNumber;
}

/** 원본 summary를 수정하지 않고 upstream이 지원하는 두 입력 형식의 범위를 읽습니다. */
export function readCompressionRanges(content: unknown): MessageRange[] {
    if (typeof content !== "string") return [];
    const ranges: MessageRange[] = [];
    const trimmedContent = content.trim();
    if (trimmedContent.startsWith("[")) {
        try {
            const entries = JSON.parse(trimmedContent);
            if (!Array.isArray(entries)) return [];
            for (const entry of entries) {
                const start = readMessageReference(entry?.startId);
                const end = readMessageReference(entry?.endId);
                if (start === undefined || end === undefined || start > end) return [];
                ranges.push({ start, end });
            }
        } catch {
            return [];
        }
        return ranges;
    }
    for (const match of content.matchAll(/^\s*(m\d+)\s*[–—-]\s*(m\d+)(?:\s|$)/gm)) {
        const start = readMessageReference(match[1]);
        const end = readMessageReference(match[2]);
        if (start === undefined || end === undefined || start > end) return [];
        ranges.push({ start, end });
    }
    return ranges;
}

/** acp_status의 추천 목록만 읽고 UNCOVERED HISTORY 등의 ref는 제외합니다. */
export function readRecommendedRanges(statusText: string): MessageRange[] | undefined {
    const headingMatch = /^Compressible ranges \(\d+[^\n]*\):\s*$/m.exec(statusText);
    if (!headingMatch) return;
    const remainingText = statusText.slice(headingMatch.index + headingMatch[0].length).trimStart();
    const rangeLines: string[] = [];
    for (const line of remainingText.split("\n")) {
        if (!/^\s*m\d+\s*[–—-]\s*m\d+\s/.test(line)) break;
        rangeLines.push(line);
    }
    return readCompressionRanges(rangeLines.join("\n"));
}

/** 분할과 인접 추천 범위의 합집합은 허용하되 범위 사이의 빈틈은 허용하지 않습니다. */
function rangesAreRecommended(requested: MessageRange[], recommended: MessageRange[]): boolean {
    const orderedRecommendations = [...recommended].sort((first, second) => first.start - second.start);
    return requested.every(range => {
        let nextReference = range.start;
        for (const recommendation of orderedRecommendations) {
            if (recommendation.end < nextReference) continue;
            if (recommendation.start > nextReference) return false;
            nextReference = recommendation.end + 1;
            if (nextReference > range.end) return true;
        }
        return false;
    });
}

/** 거대한 malformed JSON 인자를 다음 Context에 다시 싣지 않도록 오류만 남깁니다. */
function summarizeCompressionFailure(resultText: string): string {
    const argumentMarker = resultText.indexOf("Received arguments:");
    const failureText = argumentMarker < 0 ? resultText : resultText.slice(0, argumentMarker);
    return failureText.slice(0, MAXIMUM_FAILURE_TEXT_LENGTH).trim();
}

/** 실행 도구와 무관하게 압축 실패를 집계하고 Pi의 현재 run만 중단합니다. */
export function createCompressionGuard(reportStop: (message: string, context: ExtensionContext) => void) {
    let failureCount = 0;
    let statusRequired = false;
    let recommendedRanges: MessageRange[] | undefined;
    let stopped = false;
    const observedCalls = new Set<string>();

    /** 새 사용자 요청 또는 Session 전환에서만 실패 예산을 초기화합니다. */
    function reset(): void {
        failureCount = 0;
        statusRequired = false;
        recommendedRanges = undefined;
        stopped = false;
        observedCalls.clear();
    }

    /** 실패 후 최신 추천을 확인하지 않은 재시도와 확인된 범위 이탈을 실행 전에 막습니다. */
    function handleToolCall(event: ToolCallEvent) {
        if (stopped) {
            return { block: true, terminate: true, reason: "Paseo compression guard: 이 요청은 압축 실패로 중단되었습니다." };
        }
        if (event.toolName !== "compress") return;
        if (statusRequired) {
            return { block: true, reason: "Paseo compression guard: call acp_status before retrying compress. A status report does not replace a new compression nudge." };
        }
        if (recommendedRanges !== undefined) {
            const requestedRanges = readCompressionRanges(event.input.content);
            if (requestedRanges.length === 0 || !rangesAreRecommended(requestedRanges, recommendedRanges)) {
                return { block: true, reason: "Paseo compression guard: invalid or out-of-recommendation ranges. Call acp_status and copy only its listed ranges; do not extend them or repeat the rejected call." };
            }
        }
    }

    /** 실제 tool과 schema 검증·실행 전 차단의 결과를 중복 없이 같은 기준으로 처리합니다. */
    function handleToolResult(event: CompressionResult, context: ExtensionContext) {
        if (!["compress", "acp_status"].includes(event.toolName) || observedCalls.has(event.toolCallId)) return;
        observedCalls.add(event.toolCallId);
        const resultText = event.content.filter(part => part.type === "text").map(part => part.text).join("\n");
        if (event.toolName === "acp_status") {
            if (!event.isError) {
                const currentRecommendations = readRecommendedRanges(resultText);
                if (currentRecommendations !== undefined) {
                    recommendedRanges = currentRecommendations;
                    statusRequired = false;
                }
            }
            return;
        }
        const resultDetails = event.details as { outcome?: string; blocksCreated?: number } | undefined;
        if (["applied", "partial"].includes(resultDetails?.outcome ?? "") &&
            (resultDetails?.blocksCreated ?? 0) > 0) {
            failureCount = 0;
            recommendedRanges = undefined;
            statusRequired = false;
            return;
        }
        failureCount += 1;
        statusRequired = true;
        recommendedRanges = undefined;
        const failureSummary = summarizeCompressionFailure(resultText);
        const retryGuidance = resultText.includes("compress.requireNudge")
            ? "No nudge is valid for this round. Continue the task WITHOUT compress; wait for a newly delivered nudge. acp_status alone does not authorize compression."
            : "Before retrying, call acp_status, copy only its current recommended ranges, and fix the content STRING format. Do not repeat the rejected call unchanged.";
        const stopMessage = `Paseo가 압축 실패 ${failureCount}회 누적으로 현재 작업을 중단했습니다. Session과 기존 파일 변경은 유지됩니다. 압축 오류를 확인한 후 새 메시지로 다시 요청해 주세요.`;
        if (failureCount >= COMPRESSION_FAILURE_LIMIT && !stopped) {
            stopped = true;
            context.abort();
            reportStop(stopMessage, context);
        }
        return {
            isError: true,
            content: [{ type: "text" as const, text: [failureSummary,
                `[Paseo compression guard ${failureCount}/${COMPRESSION_FAILURE_LIMIT}]`,
                stopped ? stopMessage : retryGuidance].join("\n\n") }],
            details: { ...resultDetails, compressionGuard: { failureCount, stopped } },
        };
    }

    return { reset, handleToolCall, handleToolResult };
}

/** 기존 billion-context의 승인·범위 제한을 바꾸지 않고 Paseo에 실패 보호를 연결합니다. */
export function registerCompressionGuard(extensionApi: ExtensionAPI): void {
    const guard = createCompressionGuard((message, context) => {
        context.ui.notify(message, "warning");
        extensionApi.sendMessage({ customType: "paseo-compression-stop", content: message, display: true },
            { triggerTurn: false });
    });
    extensionApi.on("session_start", guard.reset);
    extensionApi.on("session_switch", guard.reset);
    extensionApi.on("before_agent_start", event => {
        if (event.messageType === "user") guard.reset();
        return { systemPrompt: `${event.systemPrompt}\n\n${COMPRESSION_INSTRUCTIONS}` };
    });
    extensionApi.on("tool_call", guard.handleToolCall);
    extensionApi.on("tool_result", guard.handleToolResult);
    extensionApi.on("message_end", (event, context) => {
        if (event.message.role !== "toolResult") return;
        // Pi는 malformed JSON과 실행 전 차단에서 tool_result hook을 생략합니다.
        const replacement = guard.handleToolResult(event.message, context);
        if (replacement) return { message: { ...event.message, ...replacement } };
    });
}
