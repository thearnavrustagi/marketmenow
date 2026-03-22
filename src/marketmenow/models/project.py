from __future__ import annotations

from pydantic import BaseModel, Field


class BrandConfig(BaseModel, frozen=True):
    """Product brand identity — name, URL, visual identity, and feature list."""

    name: str
    url: str
    tagline: str
    value_prop: str = ""
    color: str = "#000000"
    logo_letter: str = ""
    logo_suffix: str = ""
    features: list[str] = Field(default_factory=list)


class TargetCustomer(BaseModel, frozen=True):
    """Ideal customer profile used for outreach, discovery, and scoring."""

    description: str
    pain_points: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    platforms: list[str] = Field(default_factory=list)


class PersonaConfig(BaseModel, frozen=True):
    """Social media persona that drives reply generation and content voice."""

    name: str
    description: str = ""
    voice: str = ""
    tone: str = ""
    example_phrases: list[str] = Field(default_factory=list)
    platform_overrides: dict[str, dict[str, str]] = Field(default_factory=dict)


class ProjectConfig(BaseModel, frozen=True):
    """Top-level project config loaded from ``project.yaml``."""

    slug: str
    brand: BrandConfig
    target_customer: TargetCustomer | None = None
    default_persona: str = "default"
    env_overrides: dict[str, str] = Field(default_factory=dict)
