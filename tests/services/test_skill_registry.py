"""Tests for the SkillRegistry."""

from __future__ import annotations

from pathlib import Path

import pytest

from py.services.agent.skill_registry import SkillRegistry
from py.services.agent.skill_definition import SkillDefinition, SkillPermissions


@pytest.fixture
def registry():
    """Create a SkillRegistry with the real skills directory."""
    SkillRegistry.reset_instance()
    reg = SkillRegistry()
    reg._discover()
    return reg


class TestSkillRegistryDiscovery:
    def test_discovers_enrich_hf_metadata_skill(self, registry):
        skills = registry.list_skills()
        assert len(skills) >= 1
        skill = registry.get_skill("enrich_hf_metadata")
        assert skill is not None
        assert skill.name == "enrich_hf_metadata"
        assert skill.llm_required is True

    def test_skill_has_correct_model_type_filter(self, registry):
        skill = registry.get_skill("enrich_hf_metadata")
        # model_type_filter was removed from SKILL.md — defaults to None (all types)
        assert skill.model_type_filter is None

    def test_skill_has_permissions(self, registry):
        skill = registry.get_skill("enrich_hf_metadata")
        assert skill.permissions.write_metadata is True
        assert skill.permissions.write_previews is True
        # network_domains defaults to () since permissions block was removed

    def test_get_skill_returns_none_for_unknown(self, registry):
        assert registry.get_skill("nonexistent_skill") is None


class TestSkillRegistryLoading:
    def test_load_prompt_returns_content(self, registry):
        prompt = registry.load_prompt("enrich_hf_metadata")
        assert isinstance(prompt, str)
        assert len(prompt) > 100
        assert "base_model" in prompt
        assert "trigger_words" in prompt

    def test_load_prompt_raises_for_unknown_skill(self, registry):
        with pytest.raises((FileNotFoundError, ValueError)):
            registry.load_prompt("nonexistent")


class TestSkillDefinition:
    def test_applies_to_model_type_with_filter(self):
        sd = SkillDefinition(
            name="test",
            title="Test",
            description="",
            llm_required=False,
            model_type_filter=["lora"],
        )
        assert sd.applies_to_model_type("lora") is True
        assert sd.applies_to_model_type("checkpoint") is False

    def test_applies_to_model_type_without_filter(self):
        sd = SkillDefinition(
            name="test",
            title="Test",
            description="",
            llm_required=False,
            model_type_filter=None,
        )
        assert sd.applies_to_model_type("lora") is True
        assert sd.applies_to_model_type("checkpoint") is True


class TestSkillPermissions:
    def test_defaults(self):
        sp = SkillPermissions()
        assert sp.write_metadata is True
        assert sp.write_previews is True
        assert sp.network_domains == ()
