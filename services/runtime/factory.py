from services.runtime.docker_runtime import DockerRuntime
from services.runtime.vmware_runtime import VmwareRuntime


class RuntimeFactory:
    @staticmethod
    def get_runtime(scenario_type: str):
        if scenario_type == "docker":
            return DockerRuntime()
        if scenario_type == "vm":
            return VmwareRuntime()
        raise ValueError(f"Unknown scenario type: {scenario_type}")