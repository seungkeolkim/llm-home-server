"""Reload와 브라우저 재접속에도 남는 제어 작업을 SQLite로 관리합니다."""

from pathlib import Path
import json
import os
import sqlite3
import subprocess
import sys
import time
import uuid

import psutil

from .configuration import WORKSPACE_DIRECTORY


ALLOWED_OPERATIONS = {("llm", "start"), ("llm", "stop"),
                      ("librechat", "start"), ("librechat", "stop"), ("comfy", "unload")}


class OperationStore:
    """여러 브라우저의 중복 조작과 reload 중 작업 유실을 방지합니다."""

    def __init__(self, database_path=None, log_directory=None):
        """기존 서비스 DB와 분리한 제어 이력 DB를 준비합니다."""
        self.database_path = Path(database_path or WORKSPACE_DIRECTORY / "data/ManagementServer/operations.sqlite3")
        self.log_directory = Path(log_directory or (
            self.database_path.parent / "operation-logs" if database_path else
            WORKSPACE_DIRECTORY / "runtime/ManagementServer/operations"))
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS operations (
                identifier TEXT PRIMARY KEY, target TEXT NOT NULL, action TEXT NOT NULL,
                status TEXT NOT NULL, created_at REAL NOT NULL, finished_at REAL,
                worker_pid INTEGER, message TEXT NOT NULL DEFAULT '')""")
            existing_columns = {row[1] for row in connection.execute("PRAGMA table_info(operations)")}
            for column_name in ("profile_id", "configuration_revision", "instance_id"):
                if column_name not in existing_columns:
                    connection.execute(f"ALTER TABLE operations ADD COLUMN {column_name} TEXT")

    def connect(self):
        """작업별 독립 DB 연결과 dict 형태의 행을 만듭니다."""
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA synchronous = EXTRA")
        return connection

    def append_operation_log(self, identifier, status, message):
        """서비스 실행 전에 제어 단계와 시각을 기록하고 디스크에 반영합니다."""
        self.log_directory.mkdir(parents=True, exist_ok=True)
        record = {"at": time.time(), "identifier": identifier, "status": status, "message": message}
        with (self.log_directory / f"{identifier}.log").open("a", encoding="utf-8") as log_stream:
            log_stream.write(json.dumps(record, ensure_ascii=False) + "\n")
            log_stream.flush()
            os.fsync(log_stream.fileno())

    def recent(self):
        """최근 제어 작업 20개를 읽습니다."""
        with self.connect() as connection:
            return [dict(row) for row in connection.execute(
                "SELECT * FROM operations ORDER BY created_at DESC LIMIT 20")]

    def get(self, identifier):
        """지정한 작업 한 개를 조회합니다."""
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM operations WHERE identifier = ?", (identifier,)).fetchone()
        return dict(row) if row else None

    def recover_interrupted(self):
        """재부팅 또는 worker 종료로 끊긴 요청을 중단으로 기록하고 서비스를 재실행하지 않습니다."""
        with self.connect() as connection:
            active_operations = [dict(row) for row in connection.execute(
                "SELECT * FROM operations WHERE status IN ('queued', 'running')")]
        boot_time = psutil.boot_time()
        for operation in active_operations:
            previous_boot = operation["created_at"] < boot_time
            if not previous_boot and time.time() - operation["created_at"] < 15:
                continue
            is_owned_worker = False
            if not previous_boot:
                try:
                    command_line = psutil.Process(operation["worker_pid"] or -1).cmdline()
                    is_owned_worker = "management_server.worker" in command_line and operation["identifier"] in command_line
                except psutil.AccessDenied:
                    continue
                except (psutil.NoSuchProcess, ValueError):
                    pass
            if not is_owned_worker:
                message = ("시스템 재부팅으로 제어가 중단됐습니다. 당시 최종 결과는 확인할 수 없습니다."
                           if previous_boot else
                           "제어 worker가 종료되어 중단됐습니다. 실제 서비스 상태를 확인해 주세요.")
                self.finish(operation["identifier"], "interrupted", message, expected_operation=operation)

    def create(self, target, action, identifier=None, selection=None):
        """SQLite transaction으로 동시에 하나의 제어 작업만 접수합니다."""
        if (target, action) not in ALLOWED_OPERATIONS:
            raise ValueError("허용되지 않은 제어 동작입니다.")
        self.recover_interrupted()
        identifier = identifier or uuid.uuid4().hex
        if uuid.UUID(identifier).hex != identifier:
            raise ValueError("올바르지 않은 제어 요청 ID입니다.")
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            active_operation = connection.execute(
                "SELECT identifier FROM operations WHERE status IN ('queued', 'running') LIMIT 1").fetchone()
            if active_operation:
                raise RuntimeError("다른 제어 작업이 진행 중입니다.")
            existing_operation = connection.execute(
                "SELECT identifier FROM operations WHERE identifier = ?", (identifier,)).fetchone()
            if existing_operation:
                raise RuntimeError("이미 접수한 제어 요청입니다. 이력을 확인해 주세요.")
            message = "제어 요청을 저장했습니다. 실행을 기다리고 있습니다."
            connection.execute("INSERT INTO operations(identifier, target, action, status, created_at, message) VALUES(?,?,?,?,?,?)",
                               (identifier, target, action, "queued", time.time(), message))
            if selection:
                connection.execute(
                    "UPDATE operations SET profile_id=?, configuration_revision=?, instance_id=? WHERE identifier=?",
                    (selection["profile_id"], selection["configuration_revision"], selection["instance_id"], identifier))
        self.append_operation_log(identifier, "queued", f"{target}/{action}: {message}")
        return identifier

    def launch(self, identifier):
        """API server와 수명을 분리한 worker를 실행해 reload 중에도 제어를 계속합니다."""
        log_directory = self.log_directory
        log_directory.mkdir(parents=True, exist_ok=True)
        command = [sys.executable, "-B", "-m", "management_server.worker", identifier]
        creation_flags = 0
        if sys.platform == "win32":
            creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        try:
            with (log_directory / f"{identifier}.log").open("ab") as log_stream:
                process = subprocess.Popen(command, cwd=WORKSPACE_DIRECTORY, stdin=subprocess.DEVNULL,
                                           stdout=log_stream, stderr=subprocess.STDOUT,
                                           creationflags=creation_flags, close_fds=True)
            with self.connect() as connection:
                connection.execute("UPDATE operations SET worker_pid = ? WHERE identifier = ? AND status = 'queued'",
                                   (process.pid, identifier))
        except OSError:
            self.finish(identifier, "failed", "제어 worker를 실행하지 못했습니다.")
            raise

    def begin(self, identifier):
        """대기 중인 요청만 실행 상태로 바꾸고 실제 명령 실행 가능 여부를 반환합니다."""
        message = "제어 명령을 실행 중입니다. 최종 결과를 기다리고 있습니다."
        with self.connect() as connection:
            updated = connection.execute(
                "UPDATE operations SET status = 'running', worker_pid = ?, message = ? WHERE identifier = ? AND status = 'queued'",
                (os.getpid(), message, identifier))
        if not updated.rowcount:
            return False
        self.append_operation_log(identifier, "running", message)
        return True

    def finish(self, identifier, status, message, expected_operation=None):
        """완료·접수·실패 결과를 기록합니다."""
        query = ("UPDATE operations SET status = ?, message = ?, finished_at = ? "
                 "WHERE identifier = ? AND status IN ('queued', 'running')")
        parameters = [status, message, time.time(), identifier]
        if expected_operation is not None:
            # 복구 판정 중 worker가 시작되거나 완료됐다면 이전 상태로 덮어쓰지 않습니다.
            query += " AND status = ? AND worker_pid IS ?"
            parameters.extend([expected_operation["status"], expected_operation["worker_pid"]])
        with self.connect() as connection:
            updated = connection.execute(query, parameters)
        if updated.rowcount:
            self.append_operation_log(identifier, status, message)
