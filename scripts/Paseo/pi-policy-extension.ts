import fs from "node:fs";
import path from "node:path";
import { randomUUID } from "node:crypto";
import { fileURLToPath } from "node:url";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

/** 잘못된 값이나 읽기 오류에서는 수동 승인을 유지합니다. */
export function readApprovalMode(configurationPath: string): "manual" | "auto" {
    try {
        const configurationText = fs.readFileSync(configurationPath, "utf8").replace(/^\uFEFF/, "");
        const configuration = JSON.parse(configurationText);
        return configuration.approval_mode === "auto" ? "auto" : "manual";
    } catch {
        return "manual";
    }
}

/** Paseo의 승인 모드와 별개로 Subagent 차단을 유지하는 tool handler를 만듭니다. */
export function createApprovalHandler(configurationPath: string) {
    /** 변경 도구만 자동승인하거나 기존과 같은 Yes/No 확인을 요청합니다. */
    return async function handleToolApproval(toolEvent: {
        toolName: string; input: Record<string, unknown>;
    }, extensionContext: {
        hasUI: boolean; ui: { confirm: (title: string, message: string) => Promise<boolean> };
    }) {
        if (toolEvent.toolName.startsWith("acp_delegate") || toolEvent.toolName === "subagent") {
            return { block: true, reason: "이 환경에서는 Subagent를 사용할 수 없습니다." };
        }
        if (!["bash", "powershell", "write", "edit"].includes(toolEvent.toolName)) {
            return;
        }
        if (readApprovalMode(configurationPath) === "auto") {
            return;
        }
        if (!extensionContext.hasUI) {
            return { block: true, reason: "수동 승인에는 Desktop 또는 RPC 승인 UI가 필요합니다." };
        }
        const requestedOperation = ["bash", "powershell"].includes(toolEvent.toolName)
            ? String(toolEvent.input.command ?? "")
            : String(toolEvent.input.path ?? "");
        const approved = await extensionContext.ui.confirm(
            `Pi ${toolEvent.toolName} 실행 승인`, requestedOperation.slice(0, 1800),
        );
        if (!approved) {
            return { block: true, reason: "사용자가 실행을 승인하지 않았습니다." };
        }
    };
}

/** Metadata 차단·공통 turn 잠금·Paseo 전용 도구 승인을 등록합니다. */
export default function registerPaseoPolicy(extensionApi: ExtensionAPI): void {
    const workspaceDirectory = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
    const sharedLockPath = path.join(workspaceDirectory, "runtime/PiCodingAgent/agent-turn.lock");
    const ownerToken = randomUUID();
    const isInternalSession = process.argv.includes("--no-session");
    const configurationPath = path.join(workspaceDirectory, "config/Paseo/paseo.local.json");
    extensionApi.on("tool_call", createApprovalHandler(configurationPath));

    /** 현재 프로세스의 policy가 만든 공통 잠금만 해제합니다. */
    function releaseSharedTurnLock(): void {
        try {
            const lockRecord = JSON.parse(fs.readFileSync(sharedLockPath, "utf8"));
            if (lockRecord.ownerToken === ownerToken) fs.unlinkSync(sharedLockPath);
        } catch {
            return;
        }
    }

    /** 기존 Pi와 Paseo의 실제 Agent 작업을 원자적 파일 생성으로 직렬화합니다. */
    function acquireSharedTurnLock(): boolean {
        fs.mkdirSync(path.dirname(sharedLockPath), { recursive: true });
        for (let attempt = 0; attempt < 2; attempt += 1) {
            try {
                const descriptor = fs.openSync(sharedLockPath, "wx");
                try {
                    fs.writeFileSync(descriptor, JSON.stringify({ pid: process.pid, ownerToken }));
                } finally {
                    fs.closeSync(descriptor);
                }
                return true;
            } catch (error) {
                if ((error as NodeJS.ErrnoException).code !== "EEXIST") return false;
                try {
                    const lockRecord = JSON.parse(fs.readFileSync(sharedLockPath, "utf8"));
                    if (lockRecord.ownerToken === ownerToken) return true;
                    try {
                        process.kill(lockRecord.pid, 0);
                        return false;
                    } catch (processError) {
                        if ((processError as NodeJS.ErrnoException).code !== "ESRCH") return false;
                        fs.unlinkSync(sharedLockPath);
                    }
                } catch {
                    return false;
                }
            }
        }
        return false;
    }

    extensionApi.on("input", async (_event, context) => {
        if (isInternalSession) {
            context.ui.notify("Paseo 자동 Metadata용 추가 LLM 호출을 차단했습니다.", "info");
            return { action: "handled" };
        }
        if (acquireSharedTurnLock()) return { action: "continue" };
        context.ui.notify("다른 Pi Agent 작업이 진행 중입니다. 완료 후 다시 요청해 주세요.", "warning");
        return { action: "handled" };
    });
    extensionApi.on("agent_end", releaseSharedTurnLock);
    extensionApi.on("session_shutdown", releaseSharedTurnLock);
    process.once("exit", releaseSharedTurnLock);
}
