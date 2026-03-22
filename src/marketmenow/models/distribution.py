from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from marketmenow.models.content import ContentModality

_DEFAULT_MAP_PATH = Path(__file__).resolve().parents[1] / "distribution_defaults.yaml"


class DistributionRoute(BaseModel, frozen=True):
    modality: ContentModality
    platforms: frozenset[str] = Field(default_factory=frozenset)


class DistributionMap(BaseModel):
    routes: tuple[DistributionRoute, ...] = Field(default_factory=tuple)

    def platforms_for(self, modality: ContentModality) -> frozenset[str]:
        for route in self.routes:
            if route.modality == modality:
                return route.platforms
        return frozenset()

    @classmethod
    def from_yaml(cls, path: Path) -> DistributionMap:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return cls.model_validate(payload)

    @classmethod
    def defaults(cls) -> DistributionMap:
        return cls.from_yaml(_DEFAULT_MAP_PATH)
