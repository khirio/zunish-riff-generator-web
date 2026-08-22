import random
from dataclasses import dataclass

import pytest

from zunish.registry import Registry, weighted_choice


@dataclass(frozen=True)
class _Item:
    id: str


def test_register_and_get():
    registry: Registry[_Item] = Registry("item")
    registry.register(_Item(id="a"))
    registry.register(_Item(id="b"))
    assert registry.get("a").id == "a"
    assert set(registry.ids()) == {"a", "b"}
    assert len(registry) == 2
    assert "a" in registry
    assert "z" not in registry


def test_register_duplicate_raises():
    registry: Registry[_Item] = Registry("item")
    registry.register(_Item(id="a"))
    with pytest.raises(ValueError):
        registry.register(_Item(id="a"))


def test_weighted_choice_ignores_zero_weight_candidates():
    rng = random.Random(0)
    candidates = [("only", 1.0), ("never", 0.0)]
    results = {weighted_choice(rng, candidates) for _ in range(50)}
    assert results == {"only"}


def test_weighted_choice_distribution_is_biased():
    rng = random.Random(1)
    candidates = [("heavy", 99.0), ("light", 1.0)]
    results = [weighted_choice(rng, candidates) for _ in range(200)]
    assert results.count("heavy") > results.count("light")


def test_weighted_choice_requires_positive_total_weight():
    with pytest.raises(ValueError):
        weighted_choice(random.Random(0), [("a", 0.0), ("b", 0.0)])
