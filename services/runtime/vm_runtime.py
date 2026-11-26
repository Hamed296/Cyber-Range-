import random
import subprocess
from core.config import settings
from services.runtime.base import RuntimeBase, RuntimeStartResult


def _pick_port() -> int:
    return random.randint(settings.ports_start, settings.ports_end)


class VmRuntime(RuntimeBase):
    """
    VM runtime عملي عبر Docker container يقدّم noVNC (Ubuntu Desktop).
    يحقّق نفس المطلوب: جلسة مستقلة + رابط noVNC.
    """

    def start(self, user, scenario) -> RuntimeStartResult:
        novnc_port = _pick_port()
        container_name = f"cr_vm_u{user.id}_s{scenario.id}_{novnc_port}"

        cmd = [
            "docker",
            "run",
            "-d",
            "--name",
            container_name,
            "-p",
            f"{novnc_port}:6080",
            "dorowu/ubuntu-desktop-lxde-vnc",
        ]
        subprocess.run(cmd, check=True)

        access_url = f"{settings.public_base_url}/runtime/novnc/{novnc_port}"
        runtime_data = {
            "type": "vm",
            "container_name": container_name,
            "novnc_port": novnc_port,
            "access_url": access_url,
        }
        return RuntimeStartResult(access_url=access_url, runtime_data=runtime_data)

    def stop(self, runtime_data: dict) -> None:
        name = runtime_data.get("container_name")
        if not name:
            return
        subprocess.run(["docker", "rm", "-f", name], check=False)
