"""한 개의 실제 LLM instance와 profile별 Engine 수명을 관리합니다."""

from contextlib import contextmanager
import json
import os
from pathlib import Path
import socket
import subprocess
import time
import uuid

import httpx
import psutil

from .configuration import WORKSPACE_DIRECTORY, read_json, resolve_workspace_path
from .llm_profiles import ProfileCatalog


class ProfileRuntime:
    """서버 reload와 독립적인 instance 기록으로 소유 process만 제어합니다."""

    def __init__(self, configuration, runtime_directory=None):
        """상태 조회만으로 process를 시작하거나 설정을 생성하지 않습니다."""
        self.configuration = configuration
        self.catalog = ProfileCatalog(configuration)
        self.directory = Path(runtime_directory or WORKSPACE_DIRECTORY / "runtime/ManagementServer/llm")
        self.record_path = self.directory / "instance.json"
        self.native_configuration = read_json(resolve_workspace_path(configuration["configuration_path"]))

    def read_instance(self):
        """마지막 실행 instance를 읽고 손상된 기록은 조용히 덮어쓰지 않습니다."""
        if not self.record_path.exists():
            return None
        return read_json(self.record_path)

    def write_instance(self, instance):
        """완성된 instance 기록을 atomic replace로 저장합니다."""
        self.directory.mkdir(parents=True, exist_ok=True)
        temporary_path = self.record_path.with_suffix(".tmp")
        temporary_path.write_text(json.dumps(instance, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary_path, self.record_path)

    @contextmanager
    def control_lock(self):
        """다른 worker나 직접 제어와 동시에 start·stop하지 않도록 잠급니다."""
        import msvcrt
        self.directory.mkdir(parents=True, exist_ok=True)
        with (self.directory / "control.lock").open("a+b") as lock_stream:
            try:
                lock_stream.seek(0)
                if not lock_stream.read(1):
                    lock_stream.write(b"0")
                    lock_stream.flush()
                lock_stream.seek(0)
                msvcrt.locking(lock_stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                raise RuntimeError("다른 LLM 제어가 진행 중입니다.") from None
            try:
                yield
            finally:
                lock_stream.seek(0)
                msvcrt.locking(lock_stream.fileno(), msvcrt.LK_UNLCK, 1)

    def owned_process(self, instance):
        """PID 재사용을 배제하고 create time과 실제 command identity를 확인합니다."""
        if not instance or not instance.get("pid"):
            return None
        try:
            process = psutil.Process(instance["pid"])
            if abs(process.create_time() - instance["process_created_at"]) > 0.01:
                return None
            if instance.get("native_owner_id"):
                native_status = self.strata_status()
                if (native_status.get("owner_id") != instance["native_owner_id"] or
                    native_status.get("instance_id") != instance["native_instance_id"] or
                    native_status.get("child_pid") != instance["pid"]):
                    return None
                return process
            command = " ".join(process.cmdline()).replace("\\", "/").lower()
            if instance["process_marker"].lower() not in command:
                return None
            return process
        except (psutil.NoSuchProcess, psutil.AccessDenied, KeyError):
            return None

    def port_in_use(self):
        """공통 API port가 다른 process에 점유됐는지 확인합니다."""
        with socket.socket() as connection:
            connection.settimeout(0.3)
            return connection.connect_ex(("127.0.0.1", 8488)) == 0

    def pin_operation(self, action, profile_identifier=None, revision=None):
        """접수 시 대상 profile·revision 또는 실제 종료 instance를 고정합니다."""
        instance = self.read_instance()
        if action == "start":
            profile = self.catalog.get(profile_identifier)
            description = self.catalog.describe(profile)
            if description["state"] != "available":
                raise RuntimeError(description["problem"])
            if revision != description["revision"]:
                raise RuntimeError("선택 후 설정이 변경됐습니다. 목록을 새로 확인해 주세요.")
            if self.owned_process(instance) or self.port_in_use():
                raise RuntimeError("LLM이 이미 실행 중입니다. 먼저 종료해 주세요.")
            return {"profile_id": profile_identifier, "configuration_revision": revision,
                    "instance_id": uuid.uuid4().hex}
        if action != "stop":
            raise ValueError("허용되지 않은 LLM 제어입니다.")
        if not self.owned_process(instance):
            raise RuntimeError("소유한 실행 instance를 확인하지 못했습니다. Process 상태를 확인해 주세요.")
        return {"profile_id": instance["profile_id"],
                "configuration_revision": instance["configuration_revision"], "instance_id": instance["identifier"]}

    def log_path(self):
        """현재 또는 마지막 실제 profile의 등록된 로그 위치를 반환합니다."""
        instance = self.read_instance()
        profile = self.catalog.get(instance["profile_id"] if instance else next(iter(self.catalog.profiles)))
        return resolve_workspace_path(profile["log_path"])

    async def status(self, client):
        """실제 instance와 readiness를 조회하고 준비 목록을 함께 제공합니다."""
        instance = self.read_instance()
        result = {"adapter": "profiles", "name": "선택 대기", "model": "실행 중인 model 없음",
                  "port": 8488, "state": "stopped", "in_flight": 0,
                  "profiles": self.catalog.public_profiles(), "instance_id": None}
        if not self.owned_process(instance):
            if self.port_in_use():
                result.update(state="unavailable", name="관리 외 Process", model="8488 port 사용 중")
            return result
        profile = self.catalog.get(instance["profile_id"])
        configuration = self.catalog.native_configuration(profile)
        result.update(name=self.catalog.document["engines"][profile["engine"]],
                      adapter=profile["engine"], model=configuration["model_name"], state="starting",
                      instance_id=instance["identifier"], profile_id=profile["identifier"])
        try:
            response = await client.get("http://127.0.0.1:8488/v1/status", timeout=3,
                                        headers={"Authorization": "Bearer " + configuration["api_key"]})
            response.raise_for_status()
            status = response.json()
            if status.get("loaded"):
                result["in_flight"] = status.get("activity", {}).get("in_flight", 0)
                result["state"] = "generating" if result["in_flight"] else "ready"
        except (httpx.HTTPError, ValueError):
            pass
        return result

    def check_resources(self, profile):
        """다른 GPU 작업을 종료하지 않고 최소 기동 여유만 검사합니다."""
        if psutil.virtual_memory().available < profile["minimum_ram_gib"] * 1024 ** 3:
            raise RuntimeError(f"가용 system RAM이 {profile['minimum_ram_gib']} GiB 미만입니다.")
        completed = subprocess.run(["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
                                   capture_output=True, text=True, timeout=5, check=True,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        free_memory = int(completed.stdout.strip().splitlines()[0])
        if free_memory < profile["minimum_free_vram_mib"]:
            raise RuntimeError("VRAM 기동 여유가 부족합니다. 다른 GPU 작업과 reserve를 확인해 주세요.")

    def strata_command(self, action):
        """기존 Strata의 검증된 native runtime 제어를 재사용합니다."""
        return [str(WORKSPACE_DIRECTORY / ".venv/Strata/Scripts/strata-runtime-python.exe"),
                "-I", "-B", str(WORKSPACE_DIRECTORY / "scripts/Strata/strata_runner.py"), action]

    def strata_status(self):
        """보호된 Strata process는 native 소유권 RPC로 식별합니다."""
        completed = subprocess.run(self.strata_command("status"), cwd=WORKSPACE_DIRECTORY,
                                   capture_output=True, text=True, encoding="utf-8", errors="replace",
                                   timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)
        for line in reversed(completed.stdout.splitlines()):
            try:
                return json.loads(line)
            except ValueError:
                continue
        return {}

    def attach_strata_identity(self, instance):
        """native attestation·API identity가 검증된 instance만 기록에 연결합니다."""
        status = self.strata_status()
        if not (status.get("ok") and status.get("api_identity_verified") and status.get("launch_attested")
                and status.get("api_url") == "http://127.0.0.1:8488"):
            raise RuntimeError("Strata native 소유권 검증 실패")
        process = psutil.Process(status["child_pid"])
        if process.create_time() < instance["created_at"]:
            raise RuntimeError("Strata process가 접수한 기동보다 먼저 시작됐습니다.")
        instance.update(pid=process.pid, process_created_at=process.create_time(), process_marker="strata-managed",
                        native_owner_id=status["owner_id"], native_instance_id=status["instance_id"])
        self.write_instance(instance)
        return process

    def start(self, operation):
        """선택한 profile을 기동하고 실제 readiness까지 확인합니다."""
        profile = self.catalog.get(operation["profile_id"])
        self.pin_operation("start", profile["identifier"], operation["configuration_revision"])
        self.check_resources(profile)
        configuration = self.catalog.native_configuration(profile)
        instance = {"identifier": operation.get("instance_id") or uuid.uuid4().hex, "profile_id": profile["identifier"],
                    "configuration_revision": operation["configuration_revision"], "pid": None,
                    "process_created_at": None, "process_marker": "", "created_at": time.time()}
        self.write_instance(instance)
        if profile["engine"] == "strata":
            completed = subprocess.run(self.strata_command("start"), cwd=WORKSPACE_DIRECTORY, timeout=620,
                                       creationflags=subprocess.CREATE_NO_WINDOW)
            if completed.returncode:
                raise RuntimeError("Strata 기동 실패. Engine 로그를 확인해 주세요.")
            process = self.attach_strata_identity(instance)
            marker = "strata-managed"
        else:
            command = [str(WORKSPACE_DIRECTORY / ".venv/PolyStrata/Scripts/python.exe"), "-B",
                       str(WORKSPACE_DIRECTORY / "scripts/PolyStrata/serve_profile.py"),
                       "--engine", "strata", "--port", "8488", "--host", "0.0.0.0",
                       "--config", str(resolve_workspace_path(profile["configuration_path"]))]
            marker = "scripts/polystrata/serve_profile.py"
            log_path = resolve_workspace_path(profile["log_path"])
            log_path.parent.mkdir(parents=True, exist_ok=True)
            environment = os.environ.copy()
            environment.update(PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1", PYTHONUTF8="1")
            environment.pop("PYTHONPATH", None)
            environment.pop("PYTHONHOME", None)
            with log_path.open("ab") as log_stream:
                spawned = subprocess.Popen(command, cwd=WORKSPACE_DIRECTORY, env=environment,
                                           stdin=subprocess.DEVNULL, stdout=log_stream, stderr=subprocess.STDOUT,
                                           creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)
            process = psutil.Process(spawned.pid)
        instance.update(pid=process.pid, process_created_at=process.create_time(), process_marker=marker)
        self.write_instance(instance)
        deadline = time.monotonic() + 600
        with httpx.Client(trust_env=False) as client:
            while time.monotonic() < deadline:
                if not self.owned_process(instance):
                    raise RuntimeError("LLM process가 종료됐습니다. Engine 로그를 확인해 주세요.")
                try:
                    response = client.get("http://127.0.0.1:8488/v1/status", timeout=3,
                                          headers={"Authorization": "Bearer " + configuration["api_key"]})
                    response.raise_for_status()
                    models = client.get("http://127.0.0.1:8488/v1/models", timeout=3,
                                        headers={"Authorization": "Bearer " + configuration["api_key"]}).json()
                    if response.json().get("loaded") and any(
                        model["id"] == configuration["model_name"] for model in models.get("data", [])
                    ):
                        return instance
                except (httpx.HTTPError, ValueError):
                    pass
                time.sleep(1)
        raise RuntimeError("LLM readiness 제한 시간을 초과했습니다. 자동 재시작하지 않습니다.")

    def stop(self, operation):
        """접수한 실제 instance만 종료하고 모든 소유 child의 종료를 확인합니다."""
        instance = self.read_instance()
        if not instance or instance["identifier"] != operation.get("instance_id"):
            raise RuntimeError("종료 대상 instance가 변경됐습니다.")
        process = self.owned_process(instance)
        if process is None:
            raise RuntimeError("종료 대상 process identity를 확인하지 못했습니다.")
        profile = self.catalog.get(instance["profile_id"])
        if profile["engine"] == "strata":
            stop_command = [*self.strata_command("stop"), "--if-owner-id", instance["native_owner_id"],
                            "--if-instance-id", instance["native_instance_id"]]
            completed = subprocess.run(stop_command, cwd=WORKSPACE_DIRECTORY,
                                       timeout=90, creationflags=subprocess.CREATE_NO_WINDOW)
            if completed.returncode:
                raise RuntimeError("Strata 종료 실패")
        else:
            children = process.children(recursive=True)
            for child in reversed(children):
                try:
                    child.terminate()
                except psutil.NoSuchProcess:
                    pass
            process.terminate()
            _, alive = psutil.wait_procs([process, *children], timeout=20)
            if alive:
                raise RuntimeError("일부 LLM process가 아직 종료되지 않았습니다.")
        if self.owned_process(instance) or self.port_in_use():
            raise RuntimeError("종료 후에도 LLM process 또는 API listener가 남아 있습니다.")
        instance["stopped_at"] = time.time()
        self.write_instance(instance)

    def execute(self, operation):
        """worker가 접수된 대상과 설정을 고정한 상태로 한 번만 제어합니다."""
        with self.control_lock():
            if operation["action"] == "start":
                return self.start(operation)
            if operation["action"] == "stop":
                return self.stop(operation)
            raise ValueError("허용되지 않은 LLM 제어입니다.")
