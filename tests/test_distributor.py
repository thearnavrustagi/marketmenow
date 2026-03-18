from __future__ import annotations

from conftest import (
    MockAdapter,
    MockRenderer,
    MockUploader,
    make_text_post,
    make_video,
)
from marketmenow.core.distributor import ContentDistributor
from marketmenow.models.content import ContentModality
from marketmenow.models.distribution import DistributionMap, DistributionRoute
from marketmenow.registry import AdapterRegistry, PlatformBundle


def _registry_with(*names: str) -> AdapterRegistry:
    reg = AdapterRegistry()
    for name in names:
        reg.register(
            PlatformBundle(
                adapter=MockAdapter(name),
                renderer=MockRenderer(name),
                uploader=MockUploader(name),
            )
        )
    return reg


def _map_with(**modality_platforms: list[str]) -> DistributionMap:
    routes = []
    for mod_str, platforms in modality_platforms.items():
        routes.append(
            DistributionRoute(
                modality=ContentModality(mod_str),
                platforms=frozenset(platforms),
            )
        )
    return DistributionMap(routes=tuple(routes))


class TestDistribute:
    async def test_explicit_platforms_override(self) -> None:
        reg = _registry_with("twitter", "linkedin")
        dist = ContentDistributor(reg, _map_with(text_post=["twitter"]))
        result = await dist.distribute(
            make_text_post(),
            platforms=frozenset({"linkedin"}),
        )
        assert len(result.results) == 1
        assert result.results[0].platform == "linkedin"

    async def test_map_lookup(self) -> None:
        reg = _registry_with("twitter", "linkedin")
        dist = ContentDistributor(reg, _map_with(text_post=["twitter", "linkedin"]))
        result = await dist.distribute(make_text_post())
        platforms = {r.platform for r in result.results}
        assert platforms == {"twitter", "linkedin"}

    async def test_intersection_with_registered(self) -> None:
        reg = _registry_with("twitter")
        dist = ContentDistributor(reg, _map_with(text_post=["twitter", "linkedin"]))
        result = await dist.distribute(make_text_post())
        assert len(result.results) == 1
        assert result.results[0].platform == "twitter"

    async def test_empty_intersection(self) -> None:
        reg = _registry_with("reddit")
        dist = ContentDistributor(reg, _map_with(text_post=["twitter"]))
        result = await dist.distribute(make_text_post())
        assert len(result.results) == 0
        assert len(result.errors) == 0

    async def test_no_route_in_map(self) -> None:
        reg = _registry_with("twitter")
        dist = ContentDistributor(reg, DistributionMap())
        result = await dist.distribute(make_text_post())
        assert len(result.results) == 0

    async def test_default_map_used_when_none(self) -> None:
        reg = _registry_with("instagram", "linkedin")
        dist = ContentDistributor(reg)
        result = await dist.distribute(make_video())
        platforms = {r.platform for r in result.results}
        assert "instagram" in platforms or "linkedin" in platforms
