from dataclasses import dataclass, field
from typing import Tuple


@dataclass(frozen=True)
class PluginManifest:
    id: str
    name: str
    description: str
    tools: Tuple[str, ...] = field(default_factory=tuple)
    capabilities: Tuple[str, ...] = field(default_factory=tuple)
    requires_confirmation: bool = False
    enabled_by_default: bool = True
