from pydantic_settings import BaseSettings
from pydantic import Field
from pathlib import Path


class Settings(BaseSettings):
    app_name: str = "Cyber Range"
    database_url: str = Field(default="sqlite:///./database.db")

    scenarios_dir: Path = Field(default=Path(__file__).resolve().parents[1] / "scenarios")

    public_base_url: str = Field(default="http://localhost:8000")

    ports_start: int = Field(default=20000)
    ports_end: int = Field(default=40000)

    docker_bin: str = Field(default="docker")
    docker_compose_args: str = Field(default="compose")

    #  VMware Settings
    vmrun_path: str = Field(
        default=r"C:\Program Files (x86)\VMware\VMware Workstation\vmrun.exe"
    )
    vm_clones_dir: str = Field(
        default=r"E:\virtual_os\runtime_clones"
    )

    #  Pool of pre-created VMware custom networks
    # مثال:
    # VMnet20,VMnet21,VMnet22,VMnet23,VMnet24
    vmware_vmnet_pool: str = Field(
        default="VMnet10,VMnet11,VMnet12,VMnet13,VMnet14"
    )

    class Config:
        env_file = ".env"


settings = Settings()