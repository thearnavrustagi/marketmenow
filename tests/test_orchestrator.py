from __future__ import annotations

from conftest import (
    FailingAdapter,
    MockAdapter,
    MockRenderer,
    MockUploader,
    make_text_post,
)
from marketmenow.core.orchestrator import Orchestrator
from marketmenow.exceptions import UnsupportedModalityError
from marketmenow.models.campaign import Campaign, CampaignTarget
from marketmenow.models.content import ContentModality
from marketmenow.models.result import PublishResult
from marketmenow.registry import AdapterRegistry, PlatformBundle


def _target(platform: str, modality: ContentModality = ContentModality.TEXT_POST) -> CampaignTarget:
    return CampaignTarget(platform=platform, modality=modality)


def _campaign(*targets: CampaignTarget) -> Campaign:
    return Campaign(
        name="test",
        content=make_text_post(),
        targets=list(targets),
    )


class TestRunCampaign:
    async def test_all_supported(self, registry: AdapterRegistry) -> None:
        orch = Orchestrator(registry)
        result = await orch.run_campaign(_campaign(_target("mock")))
        assert len(result.results) == 1
        assert len(result.errors) == 0
        assert isinstance(result.results[0], PublishResult)

    async def test_all_unsupported(self) -> None:
        reg = AdapterRegistry()
        adapter = MockAdapter("limited", modalities=frozenset({ContentModality.VIDEO}))
        reg.register(
            PlatformBundle(
                adapter=adapter,
                renderer=MockRenderer("limited"),
                uploader=MockUploader("limited"),
            )
        )
        orch = Orchestrator(reg)
        result = await orch.run_campaign(_campaign(_target("limited", ContentModality.POLL)))
        assert len(result.results) == 0
        assert len(result.errors) == 1
        _, exc = result.errors[0]
        assert isinstance(exc, UnsupportedModalityError)

    async def test_mixed_supported_unsupported(self) -> None:
        reg = AdapterRegistry()
        adapter = MockAdapter("partial", modalities=frozenset({ContentModality.TEXT_POST}))
        reg.register(
            PlatformBundle(
                adapter=adapter,
                renderer=MockRenderer("partial"),
                uploader=MockUploader("partial"),
            )
        )
        orch = Orchestrator(reg)
        campaign = _campaign(
            _target("partial", ContentModality.TEXT_POST),
            _target("partial", ContentModality.VIDEO),
        )
        result = await orch.run_campaign(campaign)
        assert len(result.results) == 1
        assert len(result.errors) == 1

    async def test_exception_during_execute(self) -> None:
        reg = AdapterRegistry()
        reg.register(
            PlatformBundle(
                adapter=FailingAdapter("fail"),
                renderer=MockRenderer("fail"),
                uploader=MockUploader("fail"),
            )
        )
        orch = Orchestrator(reg)
        result = await orch.run_campaign(_campaign(_target("fail")))
        assert len(result.results) == 0
        assert len(result.errors) == 1
        _, exc = result.errors[0]
        assert isinstance(exc, RuntimeError)

    async def test_campaign_id_propagated(self, registry: AdapterRegistry) -> None:
        campaign = _campaign(_target("mock"))
        orch = Orchestrator(registry)
        result = await orch.run_campaign(campaign)
        assert result.campaign_id == campaign.id

    async def test_multiple_targets_same_platform(self, registry: AdapterRegistry) -> None:
        orch = Orchestrator(registry)
        campaign = _campaign(
            _target("mock", ContentModality.TEXT_POST),
            _target("mock", ContentModality.VIDEO),
        )
        result = await orch.run_campaign(campaign)
        assert len(result.results) == 2
