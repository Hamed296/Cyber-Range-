import socket
import time
import random

def is_port_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex((host, port)) != 0

def pick_free_port(host: str = "0.0.0.0", start: int = 20000, end: int = 60000, tries: int = 2000) -> int:
    for _ in range(tries):
        p = random.randint(start, end)
        if is_port_free("127.0.0.1", p):
            return p
    raise RuntimeError("No free port found in range")

def wait_tcp_open(host: str, port: int, timeout_sec: int = 90, step_sec: float = 1.0) -> None:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            if s.connect_ex((host, port)) == 0:
                return
        time.sleep(step_sec)
    raise TimeoutError(f"Port {port} did not open on {host} within {timeout_sec}s")