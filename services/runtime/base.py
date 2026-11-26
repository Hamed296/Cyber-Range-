from abc import ABC, abstractmethod
from models.scenario import Scenario
from models.user import User


class RuntimeStartResult:
    def __init__(self, access_url: str, runtime_data: dict):
        self.access_url = access_url
        self.runtime_data = runtime_data


class RuntimeBase(ABC):
    @abstractmethod
    def start(self, user: User, scenario: Scenario) -> RuntimeStartResult:
        raise NotImplementedError

    @abstractmethod
    def stop(self, runtime_data: dict) -> None:
        raise NotImplementedError
