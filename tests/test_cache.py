from evalkit.cache import ResponseCache, cache_key
from evalkit.providers.base import Request, Response


def test_roundtrip_hits_and_misses(tmp_path):
    cache = ResponseCache(tmp_path / "sub" / "c.sqlite")
    key = cache_key({"model": "m"}, Request(prompt="p"))
    assert cache.get(key) is None
    cache.put(
        key,
        "mock:m",
        Response(text="out", input_tokens=3, output_tokens=1, cost_usd=0.5, latency_ms=12.0),
    )
    hit = cache.get(key)
    assert hit is not None
    assert (hit.text, hit.input_tokens, hit.output_tokens, hit.cost_usd, hit.latency_ms) == (
        "out",
        3,
        1,
        0.5,
        12.0,
    )
    assert hit.cached
    assert (cache.hits, cache.misses) == (1, 1)
    cache.close()


def test_persists_across_instances_and_clears(tmp_path):
    path = tmp_path / "c.sqlite"
    first = ResponseCache(path)
    first.put("k", "p", Response(text="x"))
    first.close()
    second = ResponseCache(path)
    assert second.get("k") is not None
    assert second.stats()["entries"] == 1
    assert second.stats()["by_provider"] == {"p": 1}
    assert second.clear() == 1
    assert second.get("k") is None
    second.close()


def test_in_memory_cache():
    cache = ResponseCache(":memory:")
    cache.put("k", "p", Response(text="x"))
    assert cache.get("k") is not None


def test_key_depends_on_every_input():
    base = cache_key({"model": "a"}, Request(prompt="p"))
    assert base == cache_key({"model": "a"}, Request(prompt="p"))
    variants = [
        cache_key({"model": "b"}, Request(prompt="p")),
        cache_key({"model": "a"}, Request(prompt="q")),
        cache_key({"model": "a"}, Request(prompt="p", system="s")),
        cache_key({"model": "a"}, Request(prompt="p", seed=1)),
        cache_key({"model": "a"}, Request(prompt="p", repeat=1)),
    ]
    assert len({base, *variants}) == 6
