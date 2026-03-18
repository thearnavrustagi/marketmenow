from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from marketmenow.models.content import ContentModality
from marketmenow.models.distribution import DistributionMap, DistributionRoute


class TestDistributionRoute:
    def test_construction(self) -> None:
        route = DistributionRoute(
            modality=ContentModality.VIDEO,
            platforms=frozenset({"instagram", "linkedin"}),
        )
        assert route.modality == ContentModality.VIDEO
        assert "instagram" in route.platforms

    def test_frozen(self) -> None:
        route = DistributionRoute(
            modality=ContentModality.VIDEO,
            platforms=frozenset({"instagram"}),
        )
        with pytest.raises(ValidationError):
            route.modality = ContentModality.IMAGE  # type: ignore[misc]


class TestDistributionMap:
    def test_platforms_for_present(self) -> None:
        dmap = DistributionMap(
            routes=(
                DistributionRoute(
                    modality=ContentModality.VIDEO,
                    platforms=frozenset({"instagram", "linkedin"}),
                ),
            )
        )
        result = dmap.platforms_for(ContentModality.VIDEO)
        assert result == frozenset({"instagram", "linkedin"})

    def test_platforms_for_absent(self) -> None:
        dmap = DistributionMap()
        result = dmap.platforms_for(ContentModality.POLL)
        assert result == frozenset()

    def test_from_yaml(self, tmp_path: Path) -> None:
        data = {
            "routes": [
                {"modality": "video", "platforms": ["instagram", "linkedin"]},
                {"modality": "text_post", "platforms": ["twitter"]},
            ],
        }
        yaml_path = tmp_path / "routes.yaml"
        yaml_path.write_text(yaml.dump(data))

        dmap = DistributionMap.from_yaml(yaml_path)
        assert dmap.platforms_for(ContentModality.VIDEO) == frozenset({"instagram", "linkedin"})
        assert dmap.platforms_for(ContentModality.TEXT_POST) == frozenset({"twitter"})
        assert dmap.platforms_for(ContentModality.POLL) == frozenset()

    def test_defaults_loads(self) -> None:
        dmap = DistributionMap.defaults()
        video_platforms = dmap.platforms_for(ContentModality.VIDEO)
        assert "instagram" in video_platforms
        assert "linkedin" in video_platforms

    def test_defaults_thread_goes_to_twitter(self) -> None:
        dmap = DistributionMap.defaults()
        assert "twitter" in dmap.platforms_for(ContentModality.THREAD)

    def test_defaults_no_route_for_dm(self) -> None:
        dmap = DistributionMap.defaults()
        assert dmap.platforms_for(ContentModality.DIRECT_MESSAGE) == frozenset()
