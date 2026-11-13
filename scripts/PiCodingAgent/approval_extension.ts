import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import fs from "node:fs";
import path from "node:path";
import { randomUUID } from "node:crypto";

/** 변경 작업을 Desktop/Remote의 표준 Extension UI 승인과 연결합니다. */
export default function registerApprovalExtension(extensionApi: ExtensionAPI): void {
    const runtimeDirectory = path.dirname(process.env.PI_CODING_AGENT_DIR!);
    const turnLockPath = path.join(runtimeDirectory, "agent-turn.lock");
    const ownerToken = randomUUID();

    /** 현재 Pi 프로세스가 생성한 turn 잠금만 해제합니다. */
    function releaseTurnLock(): void {
        try {
            const lockRecord = JSON.parse(fs.readFileSync(turnLockPath, "utf8"));
            if (lockRecord.ownerToken === ownerToken) fs.unlinkSync(turnLockPath);
        } catch {
            return;
        }
    }

    /** Atomic file 생성으로 Desktop과 CLI 전체에서 단일 Agent turn만 허용합니다. */
    function acquireTurnLock(): boolean {
        for (let attempt = 0; attempt < 2; attempt += 1) {
            try {
                const lockDescriptor = fs.openSync(turnLockPath, "wx");
                try {
                    fs.writeFileSync(lockDescriptor, JSON.stringify({ pid: process.pid, ownerToken }));
                } finally {
                    fs.closeSync(lockDescriptor);
                }
                return true;
            } catch (error) {
                if ((error as NodeJS.ErrnoException).code !== "EEXIST") return false;
                try {
                    const lockRecord = JSON.parse(fs.readFileSync(turnLockPath, "utf8"));
                    if (lockRecord.ownerToken === ownerToken) return true;
                    try {
                        process.kill(lockRecord.pid, 0);
                        return false;
                    } catch (processError) {
                        if ((processError as NodeJS.ErrnoException).code !== "ESRCH") return false;
                        fs.unlinkSync(turnLockPath);
                    }
                } catch {
                    return false;
                }
            }
        }
        return false;
    }

    extensionApi.on("input", async (_inputEvent, extensionContext) => {
        if (acquireTurnLock()) return { action: "continue" };
        const message = "다른 Pi Agent 작업이 진행 중입니다. 완료 후 다시 요청해 주세요.";
        if (extensionContext.hasUI) extensionContext.ui.notify(message, "warning");
        return { action: "handled" };
    });
    extensionApi.on("agent_end", releaseTurnLock);
    extensionApi.on("session_shutdown", releaseTurnLock);
    process.once("exit", releaseTurnLock);

    extensionApi.on("tool_call", async (toolEvent, extensionContext) => {
        if (toolEvent.toolName.startsWith("acp_delegate") || toolEvent.toolName === "subagent") {
            return { block: true, reason: "이 환경에서는 Subagent를 사용할 수 없습니다." };
        }
        if (!["bash", "powershell", "write", "edit"].includes(toolEvent.toolName)) {
            return;
        }
        if (!extensionContext.hasUI) {
            return { block: true, reason: "변경 작업은 interactive CLI, Desktop 또는 RPC 승인 UI가 필요합니다." };
        }
        const requestedOperation = ["bash", "powershell"].includes(toolEvent.toolName)
            ? String(toolEvent.input.command ?? "")
            : String(toolEvent.input.path ?? "");
        const approved = await extensionContext.ui.confirm(
            `Pi ${toolEvent.toolName} 실행 승인`,
            requestedOperation.slice(0, 1800),
        );
        if (!approved) {
            return { block: true, reason: "사용자가 실행을 승인하지 않았습니다." };
        }
    });
}
