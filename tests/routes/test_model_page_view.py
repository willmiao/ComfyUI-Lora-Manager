from __future__ import annotations

from types import SimpleNamespace

import jinja2

from py.routes.handlers.model_handlers import ModelPageView


class DummySettings:
    def get(self, key, default=None):
        return default


class DummyI18n:
    def __init__(self):
        self.locale = None

    def set_locale(self, locale):
        self.locale = locale

    def get_translation(self, key, default=None, **_kwargs):
        return default or key

    def create_template_filter(self):
        return lambda key, *_args, **_kwargs: key


class DummyScanner:
    def __init__(self):
        self._cache = SimpleNamespace()

    async def get_cached_data(self, *_args, **_kwargs):
        return SimpleNamespace(folders=[])


class DummyService:
    def __init__(self):
        self.scanner = DummyScanner()


async def test_model_page_view_reads_version_per_request():
    template_env = jinja2.Environment(
        loader=jinja2.DictLoader({"dummy.html": "{{ version }}"}),
        autoescape=True,
    )
    view = ModelPageView(
        template_env=template_env,
        template_name="dummy.html",
        service=DummyService(),
        settings_service=DummySettings(),
        server_i18n=DummyI18n(),
        logger=SimpleNamespace(
            debug=lambda *_args, **_kwargs: None,
            error=lambda *_args, **_kwargs: None,
        ),
    )

    view._get_app_version = lambda: "1.0.2-old"
    first = await view.handle(SimpleNamespace())

    view._get_app_version = lambda: "1.0.2-new"
    second = await view.handle(SimpleNamespace())

    assert first.text == "1.0.2-old"
    assert second.text == "1.0.2-new"
