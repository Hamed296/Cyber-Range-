import os
import random
import subprocess
from pathlib import Path
from core.config import settings
from services.runtime.base import RuntimeBase, RuntimeStartResult


def _pick_port() -> int:
    return random.randint(settings.ports_start, settings.ports_end)


class DockerRuntime(RuntimeBase):
    def start(self, user, scenario) -> RuntimeStartResult:
        scenario_dir = settings.scenarios_dir / scenario.path
        compose_file = scenario_dir / "docker-compose.yml"
        if not compose_file.exists():
            raise RuntimeError(f"docker-compose.yml not found: {compose_file}")

        project_name = f"cr_u{user.id}_s{scenario.id}_{_pick_port()}"

        ttyd_port = _pick_port()
        victim_ssh_port = _pick_port()

        env = os.environ.copy()
        env["PROJECT_NAME"] = project_name
        env["TTYD_PORT"] = str(ttyd_port)
        env["VICTIM_SSH_PORT"] = str(victim_ssh_port)

        cmd = [
            settings.docker_bin,
            *settings.docker_compose_args.split(),
            "-p",
            project_name,
            "-f",
            str(compose_file),
            "up",
            "-d",
            "--build",
        ]
        subprocess.run(cmd, cwd=str(scenario_dir), env=env, check=True)

        access_url = f"http://localhost:{ttyd_port}"
        runtime_data = {
            "type": "docker",
            "project_name": project_name,
            "scenario_dir": str(scenario_dir),
            "ttyd_port": ttyd_port,
            "victim_ssh_port": victim_ssh_port,
            "access_url": access_url,
        }
        return RuntimeStartResult(access_url=access_url, runtime_data=runtime_data)

    def stop(self, runtime_data: dict) -> None:
        project_name = runtime_data.get("project_name")
        scenario_dir = runtime_data.get("scenario_dir")
        if not project_name or not scenario_dir:
            return

        compose_file = Path(scenario_dir) / "docker-compose.yml"
        cmd = [
            settings.docker_bin,
            *settings.docker_compose_args.split(),
            "-p",
            project_name,
            "-f",
            str(compose_file),
            "down",
            "-v",
        ]
        subprocess.run(cmd, cwd=str(scenario_dir), check=False)
