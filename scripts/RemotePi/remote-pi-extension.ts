import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { publishPairingArtifacts } from "./pairing-artifacts.mjs";

const workspaceDirectory = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const blockedMeshToolNames = new Set(["agent_send", "agent_request", "list_peers"]);

/** 공식 Extension의 모바일 기능을 기존 단일 Agent 정책에 맞춰 추가합니다. */
export default async function registerRemotePiExtension(extensionApi: ExtensionAPI): Promise<void> {
    const configurationPath = path.join(workspaceDirectory, "config/RemotePi/remote-pi.local.json");
    if (!fs.existsSync(configurationPath)) return;
    const configuration = JSON.parse(fs.readFileSync(configurationPath, "utf8").replace(/^\uFEFF/, ""));
    if (!configuration.enabled) return;

    const relayUrl = new URL(configuration.relay_url);
    if (relayUrl.protocol !== "https:" || !relayUrl.hostname || relayUrl.pathname !== "/") {
        throw new Error("Remote Pi에는 유효한 Self-hosted HTTPS Relay URL이 필요합니다.");
    }
    process.env.REMOTE_PI_RELAY = relayUrl.origin;
    process.env.REMOTE_PI_HOME = path.join(workspaceDirectory, "runtime/RemotePi/home");
    process.env.REMOTE_PI_DIRECT_CONFIG = JSON.stringify({
        agent_name: configuration.agent_name,
        auto_start_relay: process.env.REMOTE_PI_VERIFY_OFFLINE === "1"
            ? false : configuration.auto_start_relay,
    });

    /** 모바일 연결에 불필요한 Agent mesh 도구와 해당 skill 등록을 생략합니다. */
    function readRestrictedApiProperty(target: ExtensionAPI, propertyName: string | symbol) {
        if (propertyName === "sendMessage") {
            /** Desktop이 생략하는 QR custom message를 로컬 PNG로도 제공합니다. */
            return function sendRemoteMessage(message: Parameters<ExtensionAPI["sendMessage"]>[0], options?: Parameters<ExtensionAPI["sendMessage"]>[1]) {
                if (message.customType === "remote-pi:pair-code" && message.details) {
                    void publishPairingArtifacts(message.details).catch(() => {
                        console.error("Remote Pi pairing QR 파일 생성에 실패했습니다.");
                    });
                }
                return target.sendMessage(message, options);
            };
        }
        if (propertyName === "registerTool") {
            /** Single Agent 환경에는 Agent 간 메시지 도구를 노출하지 않습니다. */
            return function registerRemoteTool(toolDefinition: { name: string }): void {
                if (blockedMeshToolNames.has(toolDefinition.name)) return;
                target.registerTool(toolDefinition as Parameters<ExtensionAPI["registerTool"]>[0]);
            };
        }
        if (propertyName === "on") {
            /** 자동 배포되는 Agent mesh skill을 Pi resource 목록에 추가하지 않습니다. */
            return function registerRemoteEvent(eventName: string, eventHandler: (...argumentsList: unknown[]) => unknown) {
                if (eventName === "resources_discover") return;
                return (target.on as Function)(eventName, eventHandler);
            };
        }
        const propertyValue = Reflect.get(target, propertyName);
        return typeof propertyValue === "function" ? propertyValue.bind(target) : propertyValue;
    }

    const restrictedRemoteApi = new Proxy(extensionApi, { get: readRestrictedApiProperty });
    const extensionEntryPath = path.join(workspaceDirectory,
        "data/RemotePi/npm/node_modules/remote-pi/dist/index.js");
    const officialRemoteExtension = await import(pathToFileURL(extensionEntryPath).href);
    await officialRemoteExtension.default(restrictedRemoteApi);
}
