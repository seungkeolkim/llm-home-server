"""기존 Pi 설정을 보존하며 Paseo에 필요한 별도 runtime과 daemon 설정을 만듭니다."""

import json
from pathlib import Path
import shutil
import sys


WORKSPACE_DIRECTORY = Path(__file__).resolve().parents[2]
RUNTIME_DIRECTORY = WORKSPACE_DIRECTORY / "runtime/Paseo"
HOME_DIRECTORY = WORKSPACE_DIRECTORY / "data/Paseo/home"
ORIGINAL_APPROVAL_INSTRUCTION = "- 파일을 변경하거나 명령을 실행하기 전에 목적을 설명합니다. bash/write/edit은 Extension UI에서 사용자가 승인합니다."
PASEO_APPROVAL_INSTRUCTION = (
    "- 파일을 변경하거나 명령을 실행하기 전에 목적을 설명합니다. "
    "Paseo의 approval_mode가 auto이면 bash/powershell/write/edit은 사전 승인되어 추가 확인 없이 실행합니다. "
    "manual일 때는 Extension UI에서 사용자가 승인합니다."
)


def build_agent_instructions(source_instructions):
    """기존 Pi 문서의 승인 문장만 Paseo 전용 모드 안내로 바꿉니다."""
    return source_instructions.replace(ORIGINAL_APPROVAL_INSTRUCTION, PASEO_APPROVAL_INSTRUCTION)


def write_json(configuration_path, value):
    """Paseo 전용 JSON을 처음에만 만들고 이후 사용자의 편집을 보존합니다."""
    if configuration_path.exists():
        return
    configuration_path.parent.mkdir(parents=True, exist_ok=True)
    configuration_path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def prepare_paseo_configuration():
    """Paseo Provider·Extension·Desktop profile을 원래 Pi 파일과 분리합니다."""
    configuration_path = WORKSPACE_DIRECTORY / "config/Paseo/paseo.local.json"
    if not configuration_path.exists():
        shutil.copy2(str(configuration_path) + ".template", configuration_path)
    configuration = json.loads(configuration_path.read_text(encoding="utf-8-sig"))
    if configuration["listen_host"] != "127.0.0.1":
        raise ValueError("Paseo daemon은 loopback으로만 준비합니다.")
    if configuration.get("approval_mode", "manual") not in ("manual", "auto"):
        raise ValueError("Paseo approval_mode는 manual 또는 auto여야 합니다.")
    source_agent_directory = WORKSPACE_DIRECTORY / "runtime/PiCodingAgent/agent"
    agent_directory = RUNTIME_DIRECTORY / "agent"
    agent_directory.mkdir(parents=True, exist_ok=True)
    settings = json.loads((source_agent_directory / "settings.json").read_text(encoding="utf-8-sig"))
    original_approval_path = WORKSPACE_DIRECTORY / "scripts/PiCodingAgent/approval_extension.ts"
    settings["extensions"] = [
        extension_path for extension_path in settings["extensions"]
        if Path(extension_path).resolve() != original_approval_path.resolve()
    ]
    settings["extensions"].insert(0, str(WORKSPACE_DIRECTORY / "scripts/Paseo/pi-policy-extension.ts"))
    settings["sessionDir"] = str(WORKSPACE_DIRECTORY / "data/Paseo/pi-sessions")
    settings["skills"] = [str(WORKSPACE_DIRECTORY / "config/Paseo/skills")]
    settings["defaultThinkingLevel"] = "low"
    write_json(agent_directory / "settings.json", settings)
    for filename in ("models.json", "web-search.json"):
        target_path = agent_directory / filename
        if not target_path.exists():
            shutil.copy2(source_agent_directory / filename, target_path)
    agent_instructions_path = agent_directory / "AGENTS.md"
    if not agent_instructions_path.exists():
        source_instructions = (source_agent_directory / "AGENTS.md").read_text(encoding="utf-8-sig")
        agent_instructions_path.write_text(build_agent_instructions(source_instructions), encoding="utf-8")
    providers = {name: {"enabled": False} for name in ("claude", "codex", "copilot", "opencode", "omp", "antigravity", "muse")}
    providers["pi"] = {
        "command": [sys.executable, "-u", str(WORKSPACE_DIRECTORY / "scripts/Paseo/launch_pi.py")],
        "env": {"PI_CODING_AGENT_DIR": str(agent_directory),
                "PI_CODING_AGENT_SESSION_DIR": str(WORKSPACE_DIRECTORY / "data/Paseo/pi-sessions")},
        "models": [{"id": settings["defaultProvider"] + "/" + settings["defaultModel"],
                    "label": "Local Strata QFN IQ3_XXS", "isDefault": True,
                    "thinkingOptions": [
                        {"id": "off", "label": "Off"},
                        {"id": "low", "label": "Low", "isDefault": True},
                        {"id": "medium", "label": "Medium"},
                        {"id": "high", "label": "High"},
                    ]}],
    }
    daemon_configuration = {
        "version": 1,
        "daemon": {
            "listen": f"127.0.0.1:{configuration['listen_port']}",
            "hostnames": ["127.0.0.1", "localhost"],
            "relay": {"enabled": True, "endpoint": configuration["relay_endpoint"],
                      "publicEndpoint": configuration["relay_endpoint"], "useTls": True,
                      "publicUseTls": True, "requireProtectedSecurity": True},
            "mcp": {"enabled": False, "injectIntoAgents": False},
            "browserTools": {"enabled": False},
        },
        "pluginsEnabled": False,
        "agents": {"providers": providers, "idleRuntimeCleanup": False,
                   "resumeOnStartup": False,
                   "metadataGeneration": {"providers": [{"provider": "pi", "model": providers["pi"]["models"][0]["id"]}]}},
        "features": {"dictation": {"enabled": False}, "voiceMode": {"enabled": False},
                     "webUi": {"enabled": False}},
    }
    write_json(HOME_DIRECTORY / "config.json", daemon_configuration)
    write_json(RUNTIME_DIRECTORY / "desktop-profile/desktop-settings.json", {
        "version": 1, "settings": {"releaseChannel": "stable", "notifications": {"playSound": True},
            "daemon": {"manageBuiltInDaemon": False, "keepRunningAfterQuit": True}},
        "migrations": {"legacyRendererSettingsImported": True, "daemonStopOnQuitDefaultApplied": True},
    })
    for relative_directory in ("data/Paseo/pi-sessions", "data/Paseo/context/sessions", "runtime/Paseo/verification"):
        (WORKSPACE_DIRECTORY / relative_directory).mkdir(parents=True, exist_ok=True)
    print("Paseo 전용 설정 준비 완료")


if __name__ == "__main__":
    prepare_paseo_configuration()
