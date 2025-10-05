import json
from types import SimpleNamespace

import pytest
from aiohttp.test_utils import make_mocked_request

from py.routes import stats_routes as stats_module


class FakeCache:
    def __init__(self, raw_data):
        self.raw_data = raw_data


class FakeScanner:
    def __init__(self, raw_data):
        self._cache = FakeCache(raw_data)
        self._is_initializing = False

    async def get_cached_data(self):
        return self._cache

    def is_initializing(self):
        return False


class FakeServerI18n:
    def __init__(self):
        self.locale_calls = []

    def set_locale(self, locale):
        self.locale_calls.append(locale)

    def create_template_filter(self):
        def _translate(key, **_):
            return f"translated:{key}"

        return _translate

    def get_translation(self, key, *_, **__):
        return f"translated:{key}"


class FakeSettings:
    def __init__(self, language="fr"):
        self.language = language

    def get(self, key, default=None):
        if key == "language":
            return self.language
        return default


@pytest.fixture
def stats_routes(monkeypatch):
    sample_data = {
        "loras": [
            {
                "sha256": "lora-1",
                "model_name": "Lora One",
                "size": 1024,
                "base_model": "SD15",
                "folder": "loras",
                "preview_url": "",
            },
            {
                "sha256": "lora-2",
                "model_name": "Lora Two",
                "size": 2048,
                "base_model": "SD15",
                "folder": "loras",
                "preview_url": "",
            },
            {
                "sha256": "lora-3",
                "model_name": "Lora Three",
                "size": 512,
                "base_model": "SDXL",
                "folder": "loras",
                "preview_url": "",
            },
        ],
        "checkpoints": [
            {
                "sha256": "ckpt-1",
                "model_name": "Checkpoint One",
                "size": 4096,
                "base_model": "SD15",
                "folder": "checkpoints",
                "preview_url": "",
            },
            {
                "sha256": "ckpt-2",
                "model_name": "Checkpoint Two",
                "size": 1024,
                "base_model": "SDXL",
                "folder": "checkpoints",
                "preview_url": "",
            },
        ],
        "embeddings": [
            {
                "sha256": "emb-1",
                "model_name": "Embedding One",
                "size": 256,
                "base_model": "SDXL",
                "folder": "embeddings",
                "preview_url": "",
            }
        ],
    }

    fixed_today = "2024-01-15"
    previous_day = "2024-01-14"

    usage_data = {
        "total_executions": 20,
        "loras": {
            "lora-1": {
                "total": 5,
                "history": {
                    fixed_today: 3,
                    previous_day: 2,
                },
            }
        },
        "checkpoints": {
            "ckpt-1": {
                "total": 4,
                "history": {
                    fixed_today: 4,
                },
            }
        },
        "embeddings": {},
    }

    lora_scanner = FakeScanner(sample_data["loras"])
    checkpoint_scanner = FakeScanner(sample_data["checkpoints"])
    embedding_scanner = FakeScanner(sample_data["embeddings"])

    async def fake_get_lora_scanner(cls):  # type: ignore[unused-argument]
        return lora_scanner

    async def fake_get_checkpoint_scanner(cls):  # type: ignore[unused-argument]
        return checkpoint_scanner

    async def fake_get_embedding_scanner(cls):  # type: ignore[unused-argument]
        return embedding_scanner

    monkeypatch.setattr(
        stats_module.ServiceRegistry,
        "get_lora_scanner",
        classmethod(fake_get_lora_scanner),
    )
    monkeypatch.setattr(
        stats_module.ServiceRegistry,
        "get_checkpoint_scanner",
        classmethod(fake_get_checkpoint_scanner),
    )
    monkeypatch.setattr(
        stats_module.ServiceRegistry,
        "get_embedding_scanner",
        classmethod(fake_get_embedding_scanner),
    )

    class FakeUsageStats:
        def __init__(self):
            self._data = usage_data

        async def get_stats(self):
            return self._data

    monkeypatch.setattr(stats_module, "UsageStats", FakeUsageStats)

    fake_server = FakeServerI18n()
    monkeypatch.setattr(stats_module, "server_i18n", fake_server)

    fake_settings = FakeSettings()
    monkeypatch.setattr(stats_module, "settings", fake_settings)

    real_datetime = stats_module.datetime

    class FixedDatetime(real_datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is not None:
                return real_datetime(2024, 1, 15, tzinfo=tz)
            return real_datetime(2024, 1, 15)

    monkeypatch.setattr(stats_module, "datetime", FixedDatetime)

    routes = stats_module.StatsRoutes()

    return SimpleNamespace(
        routes=routes,
        data=sample_data,
        usage=usage_data,
        server_i18n=fake_server,
        settings=fake_settings,
        today=fixed_today,
        previous_day=previous_day,
    )


@pytest.mark.asyncio
async def test_get_collection_overview(stats_routes):
    request = make_mocked_request("GET", "/api/lm/stats/collection-overview")

    response = await stats_routes.routes.get_collection_overview(request)
    payload = json.loads(response.text)

    assert payload["success"] is True

    data = stats_routes.data
    usage = stats_routes.usage
    expected_total_models = sum(len(data[key]) for key in ("loras", "checkpoints", "embeddings"))
    expected_total_size = sum(
        item.get("size", 0)
        for models in data.values()
        for item in models
    )

    assert payload["data"]["total_models"] == expected_total_models
    assert payload["data"]["total_size"] == expected_total_size
    assert payload["data"]["total_generations"] == usage["total_executions"]

    unused_loras = len([m for m in data["loras"] if m["sha256"] not in usage["loras"]])
    unused_checkpoints = len([m for m in data["checkpoints"] if m["sha256"] not in usage["checkpoints"]])
    unused_embeddings = len([m for m in data["embeddings"] if m["sha256"] not in usage["embeddings"]])

    assert payload["data"]["unused_loras"] == unused_loras
    assert payload["data"]["unused_checkpoints"] == unused_checkpoints
    assert payload["data"]["unused_embeddings"] == unused_embeddings


@pytest.mark.asyncio
async def test_get_usage_analytics(stats_routes):
    request = make_mocked_request("GET", "/api/lm/stats/usage-analytics")

    response = await stats_routes.routes.get_usage_analytics(request)
    payload = json.loads(response.text)

    assert payload["success"] is True

    top_loras = payload["data"]["top_loras"]
    assert top_loras[0]["name"] == "Lora One"
    assert top_loras[0]["usage_count"] == stats_routes.usage["loras"]["lora-1"]["total"]

    timeline = payload["data"]["usage_timeline"]
    assert len(timeline) == 30
    today_entry = timeline[-1]
    assert today_entry["date"] == stats_routes.today
    assert today_entry["lora_usage"] == 3
    assert today_entry["checkpoint_usage"] == 4
    assert today_entry["embedding_usage"] == 0
    assert today_entry["total_usage"] == 7

    previous_entry = timeline[-2]
    assert previous_entry["date"] == stats_routes.previous_day
    assert previous_entry["lora_usage"] == 2


@pytest.mark.asyncio
async def test_get_storage_analytics(stats_routes):
    request = make_mocked_request("GET", "/api/lm/stats/storage-analytics")

    response = await stats_routes.routes.get_storage_analytics(request)
    payload = json.loads(response.text)

    assert payload["success"] is True

    lora_storage = payload["data"]["loras"]
    assert [entry["name"] for entry in lora_storage] == [
        "Lora Two",
        "Lora One",
        "Lora Three",
    ]
    assert lora_storage[1]["usage_count"] == stats_routes.usage["loras"]["lora-1"]["total"]

    checkpoint_storage = payload["data"]["checkpoints"]
    assert [entry["name"] for entry in checkpoint_storage] == [
        "Checkpoint One",
        "Checkpoint Two",
    ]
    assert checkpoint_storage[0]["usage_count"] == stats_routes.usage["checkpoints"]["ckpt-1"]["total"]

    embedding_storage = payload["data"]["embeddings"]
    assert embedding_storage[0]["name"] == "Embedding One"
    assert embedding_storage[0]["usage_count"] == 0


@pytest.mark.asyncio
async def test_get_insights(stats_routes):
    request = make_mocked_request("GET", "/api/lm/stats/insights")

    response = await stats_routes.routes.get_insights(request)
    payload = json.loads(response.text)

    assert payload["success"] is True

    insights = payload["data"]["insights"]
    assert len(insights) == 3

    titles = {entry["title"] for entry in insights}
    assert "High Number of Unused LoRAs" in titles
    assert "Unused Checkpoints Detected" in titles
    assert "High Number of Unused Embeddings" in titles

    descriptions = {entry["description"] for entry in insights}
    assert any("2/3" in desc for desc in descriptions)
    assert any("1/2" in desc for desc in descriptions)
    assert any("1/1" in desc for desc in descriptions)


@pytest.mark.asyncio
async def test_handle_stats_page_renders_template(stats_routes):
    stats_routes.settings.language = "ja"

    template_context = {}

    class FakeTemplate:
        def render(self, **context):
            template_context.update(context)
            return "rendered"

    class FakeEnvironment:
        def __init__(self):
            self.filters = {}

        def get_template(self, name):
            assert name == "statistics.html"
            return FakeTemplate()

    stats_routes.routes.template_env = FakeEnvironment()

    request = make_mocked_request("GET", "/statistics")

    response = await stats_routes.routes.handle_stats_page(request)

    assert response.status == 200
    assert response.text == "rendered"
    assert stats_routes.server_i18n.locale_calls[-1] == "ja"
    assert stats_routes.routes.template_env._i18n_filter_added is True
    assert "t" in stats_routes.routes.template_env.filters
    assert stats_routes.routes.template_env.filters["t"]("greeting") == "translated:greeting"
    assert template_context["is_initializing"] is False
    assert template_context["settings"] is stats_routes.settings
    assert template_context["t"]("hello") == "translated:hello"


@pytest.mark.asyncio
async def test_handle_stats_page_handles_template_errors(stats_routes):
    stats_routes.settings.language = "es"

    class ExplodingEnvironment:
        def __init__(self):
            self.filters = {}

        def get_template(self, name):
            raise RuntimeError("boom")

    stats_routes.routes.template_env = ExplodingEnvironment()

    request = make_mocked_request("GET", "/statistics")

    response = await stats_routes.routes.handle_stats_page(request)

    assert response.status == 500
    assert response.text == "Error loading statistics page"
    assert stats_routes.server_i18n.locale_calls[-1] == "es"

