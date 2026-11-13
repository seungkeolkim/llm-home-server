"""Pi의 격리 설정과 Desktop profile을 비밀값 복사 없이 준비합니다."""

from pathlib import Path
import json
import shutil
import time

from service_runtime import (WORKSPACE_DIRECTORY, RUNTIME_DIRECTORY, PACKAGE_DIRECTORY,
                             CONFIGURATION_PATH, load_configuration, read_provider_configuration)


def write_json(configuration_path, configuration):
    """기존 Pi 설정은 백업하고 읽기 쉬운 JSON으로 저장합니다."""
    configuration_path.parent.mkdir(parents=True, exist_ok=True)
    if configuration_path.exists():
        backup_directory = WORKSPACE_DIRECTORY / "data/PiCodingAgent/backups" / str(time.time_ns())
        backup_directory.mkdir(parents=True, exist_ok=True)
        shutil.copy2(configuration_path, backup_directory / configuration_path.name)
    configuration_path.write_text(json.dumps(configuration, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def prepare_configuration():
    """기존 모델 설정은 읽기만 하고 Pi의 별도 Provider를 생성합니다."""
    configuration_directory = WORKSPACE_DIRECTORY / "config/PiCodingAgent"
    for configuration_name in ("pi-coding-agent.local.json", "billion-context.local.json"):
        configuration_path = configuration_directory / configuration_name
        if not configuration_path.exists():
            shutil.copy2(str(configuration_path) + ".template", configuration_path)
    configuration = load_configuration()
    agent_directory = RUNTIME_DIRECTORY / "agent"
    for directory_name in ("agent", "context/sessions", "desktop/sdk/current", "browser", "xdg/state"):
        (RUNTIME_DIRECTORY / directory_name).mkdir(parents=True, exist_ok=True)
    provider_models = {}
    for provider_name, provider in configuration["providers"].items():
        native_configuration = read_provider_configuration(provider)
        provider_models[provider_name] = {
            "baseUrl": f"http://127.0.0.1:{configuration['gateway_port']}/{provider['gateway_route']}/v1",
            "api": "openai-completions",
            "apiKey": "${" + provider["environment_key"] + "}",
            "models": [{
                "id": native_configuration["model_name"], "name": provider["label"],
                "reasoning": True, "input": ["text", "image"],
                "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0},
                "contextWindow": provider["context_tokens"], "maxTokens": 16384,
                "compat": {"supportsDeveloperRole": False, "maxTokensField": "max_tokens"},
            }],
        }
    write_json(agent_directory / "models.json", {"providers": provider_models})
    default_provider_name = configuration["default_provider"]
    settings = {
        "defaultProvider": default_provider_name,
        "defaultModel": provider_models[default_provider_name]["models"][0]["id"],
        "enabledModels": ["strata-local/*", "infernix-local/*"],
        "defaultThinkingLevel": "off", "cacheWarming": "off", "transport": "sse",
        "compaction": {"enabled": True, "reserveTokens": 24576, "keepRecentTokens": 32768},
        "retry": {"enabled": False, "provider": {"maxRetries": 0}},
        "shellPath": "C:/Program Files/Git/bin/bash.exe",
        "extensions": [
            "-builtin:mcp", "-builtin:llama.cpp", "-builtin:codemode", "-builtin:tool-search",
            str(PACKAGE_DIRECTORY / "node_modules/billion-context/dist/agent/pi-native.js"),
            str(PACKAGE_DIRECTORY / "node_modules/pi-web-access/dist/index.js"),
            str(WORKSPACE_DIRECTORY / "scripts/PiCodingAgent/approval_extension.ts"),
        ],
        "skills": [str(WORKSPACE_DIRECTORY / "config/PiCodingAgent/skills")],
    }
    write_json(agent_directory / "settings.json", settings)
    shutil.copy2(configuration_directory / "web-search.json.template", agent_directory / "web-search.json")
    shutil.copy2(configuration_directory / "AGENTS.md", agent_directory / "AGENTS.md")
    desktop_settings_path = RUNTIME_DIRECTORY / "desktop/pi-desktop.json"
    if not desktop_settings_path.exists():
        write_json(desktop_settings_path, {
            "language": "en", "agentRuntime": {"mode": "host", "distro": None},
            "maxSessionWorkers": 1, "autoCheckRegistryUpdates": False,
            "autoOpenLastProject": False, "recentProjects": [str(WORKSPACE_DIRECTORY)],
            "currentProject": str(WORKSPACE_DIRECTORY),
            "browserChromeBridge": {"enabled": False, "port": 19825, "token": ""},
            "sessionCapabilities": {},
        })
    write_json(RUNTIME_DIRECTORY / "desktop/sdk/current.json", {"active": "user", "userDir": "current"})
    print("Pi 설정 준비 완료. 기존 LLM 설정과 API key 저장소는 변경하지 않았습니다.")


if __name__ == "__main__":
    prepare_configuration()
