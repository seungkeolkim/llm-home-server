"""Reload와 브라우저 재접속에도 남는 제어 작업을 SQLite로 관리합니다."""

from pathlib import Path
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

    def __init__(self, database_path=None):
        """기존 서비스 DB와 분리한 제어 이력 DB를 준비합니다."""
        self.database_path = Path(database_path or WORKSPACE_DIRECTORY / "data/ManagementServer/operations.sqlite3")
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS operations (
                identifier TEXT PRIMARY KEY, target TEXT NOT NULL, action TEXT NOT NULL,
                status TEXT NOT NULL, created_at REAL NOT NULL, finished_at REAL,
                worker_pid INTEGER, message TEXT NOT NULL DEFAULT '')""")

    def connect(self):
        """작업별 독립 DB 연결과 dict 형태의 행을 만듭니다."""
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

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
        """죽은 worker의 기록만 실패 처리하며 서비스나 작업을 자동 재시작하지 않습니다."""
        for operation in self.recent():
            if operation["status"] not in {"queued", "running"} or time.time() - operation["created_at"] < 15:
                continue
            try:
                command_line = psutil.Process(operation["worker_pid"] or -1).cmdline()
                is_owned_worker = "management_server.worker" in command_line and operation["identifier"] in command_line
            except (psutil.Error, ValueError):
                is_owned_worker = False
            if not is_owned_worker:
                self.finish(operation["identifier"], "failed", "제어 worker가 종료됐습니다. 실제 서비스 상태를 확인해 주세요.")

    def create(self, target, action):
        """SQLite transaction으로 동시에 하나의 제어 작업만 접수합니다."""
        if (target, action) not in ALLOWED_OPERATIONS:
            raise ValueError("허용되지 않은 제어 동작입니다.")
        self.recover_interrupted()
        identifier = uuid.uuid4().hex
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            active_operation = connection.execute(
                "SELECT identifier FROM operations WHERE status IN ('queued', 'running') LIMIT 1").fetchone()
            if active_operation:
                raise RuntimeError("다른 제어 작업이 진행 중입니다.")
            connection.execute("INSERT INTO operations(identifier, target, action, status, created_at) VALUES(?,?,?,?,?)",
                               (identifier, target, action, "queued", time.time()))
        return identifier

    def launch(self, identifier):
        """API server와 수명을 분리한 worker를 실행해 reload 중에도 제어를 계속합니다."""
        log_directory = WORKSPACE_DIRECTORY / "runtime/ManagementServer/operations"
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
        """worker 자신의 PID와 실행 상태를 기록합니다."""
        import os
        with self.connect() as connection:
            connection.execute("UPDATE operations SET status = 'running', worker_pid = ? WHERE identifier = ?",
                               (os.getpid(), identifier))

    def finish(self, identifier, status, message):
        """완료·접수·실패 결과를 기록합니다."""
        with self.connect() as connection:
            connection.execute("UPDATE operations SET status = ?, message = ?, finished_at = ? WHERE identifier = ?",
                               (status, message, time.time(), identifier))
