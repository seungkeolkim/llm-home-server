"""고정 Engine·model catalog와 실행 설정의 검증·revision을 관리합니다."""

import hashlib
import json
from pathlib import Path

from .configuration import read_json, resolve_workspace_path


class ProfileCatalog:
    """화면에는 secret과 executable 인자를 제외한 준비 상태만 제공합니다."""

    def __init__(self, configuration):
        """설정된 catalog를 읽고 ID·Engine·model 참조를 검증합니다."""
        self.path = resolve_workspace_path(configuration["catalog_path"])
        self.document = read_json(self.path)
        self.profiles = {}
        for profile in self.document["profiles"]:
            identifier = profile["identifier"]
            if identifier in self.profiles:
                raise ValueError("중복된 LLM profile입니다.")
            if profile["engine"] not in {"strata", "polystrata"}:
                raise ValueError("지원하지 않는 Engine adapter입니다.")
            self.document["engines"][profile["engine"]]
            self.document["models"][profile["model"]]
            self.profiles[identifier] = profile

    def get(self, identifier):
        """서버에서 등록한 profile만 반환합니다."""
        if identifier not in self.profiles:
            raise ValueError("등록되지 않은 LLM profile입니다.")
        return self.profiles[identifier]

    def native_configuration(self, profile):
        """선택한 Engine의 비공개 local 설정을 읽습니다."""
        return read_json(resolve_workspace_path(profile["configuration_path"]))

    def revision(self, profile):
        """접수 후 설정 변경을 감지하되 설정 내용은 이력에 노출하지 않습니다."""
        payload = {"profile": profile, "model": self.document["models"][profile["model"]],
                   "configuration": self.native_configuration(profile)}
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

    def describe(self, profile):
        """모델을 Load하거나 다운로드하지 않고 파일 준비 상태를 확인합니다."""
        result = {"identifier": profile["identifier"], "engine": profile["engine"],
                  "engine_label": self.document["engines"][profile["engine"]],
                  "model_label": self.document["models"][profile["model"]]["label"],
                  "variant_label": profile.get("variant_label", ""),
                  "quantization": profile.get("quantization", "미등록"),
                  "context_tokens": self.document["models"][profile["model"]]["context_tokens"],
                  "label": profile["label"], "state": "available", "problem": ""}
        download_status_path = profile.get("download_status_path")
        if download_status_path and resolve_workspace_path(download_status_path).is_file():
            download_status = read_json(resolve_workspace_path(download_status_path))
            if download_status.get("state") in {"downloading", "retrying", "verifying"}:
                result.update(state="downloading", problem="Model 다운로드·검증 진행 중")
                return result
        try:
            configuration = self.native_configuration(profile)
            result["model_name"] = configuration["model_name"]
            result["revision"] = self.revision(profile)
            if configuration["port"] != 8488:
                raise ValueError("공통 API port는 8488이어야 합니다.")
            if not configuration.get("api_key") or configuration["api_key"].startswith("CHANGE_ME"):
                raise ValueError("API key 설정이 필요합니다.")
            arguments = configuration["args"]
            required_context = result["context_tokens"]
            if int(arguments[arguments.index("--max-context") + 1]) != required_context:
                raise ValueError("Engine과 catalog의 context가 다릅니다.")
            if profile["engine"] == "polystrata":
                if not Path(configuration["exe"]).is_file():
                    result.update(state="engine_missing", problem="PolyStrata Engine 미설치")
                else:
                    required_files = [Path(arguments[arguments.index("--model") + 1]),
                                      Path(configuration["tokenizer"]) / "tokenizer.json",
                                      Path(configuration["vision"]["mmproj"]),
                                      Path(configuration["vision"]["exe"]),
                                      resolve_workspace_path(".venv/PolyStrata/Scripts/python.exe")]
                    if not all(path.is_file() for path in required_files):
                        result.update(state="files_missing", problem="Model·tokenizer·Vision·runtime 준비 필요")
            elif not resolve_workspace_path(".venv/Strata/Scripts/strata-runtime-python.exe").is_file():
                result.update(state="engine_missing", problem="Strata runtime 미설치")
        except FileNotFoundError:
            result.update(state="not_configured", problem="Local 설정 또는 파일이 없습니다.")
        except (KeyError, ValueError, TypeError, OSError):
            result.update(state="invalid", problem="설정·context·파일 검증 실패")
        return result

    def public_profiles(self):
        """고정 목록 전체의 안전한 표시 정보를 반환합니다."""
        return [self.describe(profile) for profile in self.profiles.values()]
