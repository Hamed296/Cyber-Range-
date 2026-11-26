from dataclasses import dataclass
from typing import Any, Dict

@dataclass
class RuntimeResult:
    access_url: str
    runtime_data: Dict[str, Any]