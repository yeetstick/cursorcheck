"""Owned process-tree lifecycle on Windows (Job Object) and POSIX (session)."""

import json
import os
import signal
import subprocess
import sys


class Worker:
    def __init__(self, argv: list[str], *, cwd, env):
        self.job = None
        self.process = None
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes

            api = ctypes.WinDLL("kernel32", use_last_error=True)
            api.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
            api.CreateJobObjectW.restype = wintypes.HANDLE
            api.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
            api.AssignProcessToJobObject.restype = wintypes.BOOL
            api.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
            api.TerminateJobObject.restype = wintypes.BOOL
            api.CloseHandle.argtypes = [wintypes.HANDLE]
            api.CloseHandle.restype = wintypes.BOOL
            api.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
            api.SetInformationJobObject.restype = wintypes.BOOL
            class BasicLimits(ctypes.Structure):
                _fields_ = [("process_time", ctypes.c_longlong), ("job_time", ctypes.c_longlong),
                            ("flags", wintypes.DWORD), ("min_working", ctypes.c_size_t),
                            ("max_working", ctypes.c_size_t), ("active", wintypes.DWORD),
                            ("affinity", ctypes.c_size_t), ("priority", wintypes.DWORD),
                            ("scheduling", wintypes.DWORD)]
            class ExtendedLimits(ctypes.Structure):
                _fields_ = [("basic", BasicLimits), ("io", ctypes.c_ulonglong * 6),
                            ("process_memory", ctypes.c_size_t), ("job_memory", ctypes.c_size_t),
                            ("peak_process", ctypes.c_size_t), ("peak_job", ctypes.c_size_t)]
            self.api = api
            self.job = api.CreateJobObjectW(None, None)
            if not self.job:
                raise ctypes.WinError(ctypes.get_last_error())
            try:
                limits = ExtendedLimits()
                limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
                if not api.SetInformationJobObject(self.job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
                    raise ctypes.WinError(ctypes.get_last_error())
                # The wrapper cannot launch user code until assigned to the job.
                self.process = subprocess.Popen(
                    [sys.executable, "-m", "cursorcheck.supervisor"], cwd=cwd, env=env,
                    stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if not api.AssignProcessToJobObject(self.job, int(self.process._handle)):
                    raise ctypes.WinError(ctypes.get_last_error())
                self.process.stdin.write(json.dumps(argv).encode("utf-8"))
                self.process.stdin.close()
            except BaseException:
                self.close()
                raise
        else:
            self.process = subprocess.Popen(argv, cwd=cwd, env=env, start_new_session=True,
                                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def poll(self):
        return self.process.poll()

    def wait(self, timeout=None):
        return self.process.wait(timeout=timeout)

    def close(self):
        if self.job:
            self.api.TerminateJobObject(self.job, 1)
            self.api.CloseHandle(self.job)
            self.job = None
        elif self.process is not None and os.name != "nt":
            try:
                os.killpg(self.process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        if self.process is not None:
            if self.process.poll() is None:
                self.process.kill()
            self.process.wait(timeout=5)
            if self.process.stdin and not self.process.stdin.closed:
                self.process.stdin.close()


if __name__ == "__main__":
    command = json.loads(sys.stdin.buffer.read())
    code = subprocess.call(command, stdin=subprocess.DEVNULL)
    raise SystemExit(code if code >= 0 else 128 - code)
