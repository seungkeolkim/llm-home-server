"""기존 YAML과 주석을 보존하며 공통 LLM endpoint에 Infernix 고정 모델을 등록합니다."""

import copy
from datetime import datetime
import json
from pathlib import Path
import shutil
import sys

import yaml


WORKSPACE_DIRECTORY = Path(__file__).resolve().parents[2]
MODEL_IDENTIFIER = "infernix-orcarouter-qwen3.8-flash-next-nvfp4"
CONTEXT_TOKENS = 262144
SPECIFICATION_NAME = "infernix-orcarouter-nvfp4"
PROFILE_DESCRIPTION = "Uncensored · DFlash2 · KV INT8 · 262K · Vision RAM offload (GPU encode)"
LEGACY_PROFILE_DESCRIPTION = "Uncensored · DFlash2 · KV INT8 · 262K · Text only"


def mapping_value(mapping_node, key):
    """YAML 위치 정보를 가진 mapping에서 지정한 key의 값을 찾습니다."""
    for key_node, value_node in mapping_node.value:
        if key_node.value == key:
            return value_node
    raise ValueError(f"LibreChat YAML 항목이 없습니다: {key}")


def add_model_configuration(configuration_text):
    """필요한 세 목록만 편집하고 나머지 YAML의 의미와 주석을 그대로 유지합니다."""
    document = yaml.safe_load(configuration_text)
    expected = copy.deepcopy(document)
    root_node = yaml.compose(configuration_text)
    endpoint_nodes = mapping_value(mapping_value(root_node, "endpoints"), "custom")
    endpoint_index = next((index for index, endpoint in enumerate(document["endpoints"]["custom"])
                           if endpoint["name"] == "Strata"), None)
    if endpoint_index is None:
        raise ValueError("공통 Strata endpoint가 없습니다. 자동으로 다른 endpoint를 만들지 않습니다.")
    endpoint = document["endpoints"]["custom"][endpoint_index]
    expected_endpoint = expected["endpoints"]["custom"][endpoint_index]
    endpoint_node = endpoint_nodes.value[endpoint_index]
    lines = configuration_text.splitlines(keepends=True)
    newline = "\r\n" if "\r\n" in configuration_text else "\n"
    edits = []
    defaults = endpoint["models"]["default"]
    if MODEL_IDENTIFIER not in defaults:
        defaults_node = mapping_value(mapping_value(endpoint_node, "models"), "default")
        if not defaults_node.value:
            raise ValueError("기존 model 목록이 비어 있습니다.")
        indentation = defaults_node.value[0].start_mark.column - 2
        fragment = " " * indentation + "- " + MODEL_IDENTIFIER + newline
        edits.append((defaults_node.end_mark.line, defaults_node.end_mark.line, fragment))
        expected_endpoint["models"]["default"].append(MODEL_IDENTIFIER)
    token_configuration = {"prompt": 0, "completion": 0, "context": CONTEXT_TOKENS}
    if MODEL_IDENTIFIER in endpoint["tokenConfig"]:
        if endpoint["tokenConfig"][MODEL_IDENTIFIER] != token_configuration:
            raise ValueError("기존 Infernix tokenConfig가 예상한 Context와 다릅니다.")
    else:
        token_node = mapping_value(endpoint_node, "tokenConfig")
        indentation = token_node.value[0][0].start_mark.column
        fragment = " " * indentation + MODEL_IDENTIFIER + ":" + newline
        for key, value in token_configuration.items():
            fragment += " " * (indentation + 2) + f"{key}: {value}" + newline
        edits.append((token_node.end_mark.line, token_node.end_mark.line, fragment))
        expected_endpoint["tokenConfig"][MODEL_IDENTIFIER] = token_configuration
    specifications = document["modelSpecs"]["list"]
    existing_specification = next((entry for entry in specifications if entry["name"] == SPECIFICATION_NAME), None)
    if existing_specification:
        if (existing_specification["preset"]["model"] != MODEL_IDENTIFIER or
                existing_specification["preset"]["maxContextTokens"] != CONTEXT_TOKENS):
            raise ValueError("기존 Infernix modelSpec이 고정 Model ID·Context와 다릅니다.")
        if existing_specification.get("description") == LEGACY_PROFILE_DESCRIPTION:
            specification_index = specifications.index(existing_specification)
            specification_node = mapping_value(mapping_value(root_node, "modelSpecs"), "list").value[specification_index]
            description_node = mapping_value(specification_node, "description")
            indentation = specification_node.start_mark.column
            fragment = " " * indentation + "description: " + PROFILE_DESCRIPTION + newline
            edits.append((description_node.start_mark.line, description_node.end_mark.line + 1, fragment))
            expected["modelSpecs"]["list"][specification_index]["description"] = PROFILE_DESCRIPTION
    else:
        specification = {
            "name": SPECIFICATION_NAME,
            "label": "Infernix · Orcarouter NVFP4",
            "description": PROFILE_DESCRIPTION,
            "preset": {"endpoint": endpoint["name"], "model": MODEL_IDENTIFIER,
                       "maxContextTokens": CONTEXT_TOKENS},
        }
        specification_node = mapping_value(mapping_value(root_node, "modelSpecs"), "list")
        indentation = specification_node.value[0].start_mark.column - 2
        fragment_lines = yaml.safe_dump([specification], allow_unicode=True, sort_keys=False).splitlines()
        fragment = "".join(" " * indentation + line + newline for line in fragment_lines)
        edits.append((specification_node.end_mark.line, specification_node.end_mark.line, fragment))
        expected["modelSpecs"]["list"].append(specification)
    for start_line, end_line, fragment in sorted(edits, key=lambda edit: edit[0], reverse=True):
        lines[start_line:end_line] = [fragment]
    result = "".join(lines)
    if yaml.safe_load(result) != expected:
        raise ValueError("LibreChat YAML 변경 검증 실패; 기존 파일을 보존합니다.")
    return result


def main():
    """Local YAML은 백업한 뒤 등록하며 Container를 재시작하지 않습니다."""
    for filename in ("librechat.local.yaml.template", "librechat.local.yaml"):
        configuration_path = WORKSPACE_DIRECTORY / "config/LibreChat" / filename
        if not configuration_path.is_file():
            continue
        original_text = configuration_path.read_bytes().decode("utf-8-sig")
        updated_text = add_model_configuration(original_text)
        if updated_text == original_text:
            print(f"Already configured: {filename}")
            continue
        if filename == "librechat.local.yaml":
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            backup_path = WORKSPACE_DIRECTORY / "data/Infernix/backups" / timestamp / filename
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(configuration_path, backup_path)
        configuration_path.write_bytes(updated_text.encode("utf-8"))
        print(f"Configured: {filename}; model={MODEL_IDENTIFIER}; context={CONTEXT_TOKENS}")


if __name__ == "__main__":
    main()
