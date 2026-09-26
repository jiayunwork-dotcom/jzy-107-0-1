"""pytest 公共夹具：每个测试都拿独立的通道档存储，互不污染。"""

from __future__ import annotations

import pytest

from app import create_app
from app.profiles import ProfileStore, make_default_store


@pytest.fixture()
def store() -> ProfileStore:
    """空的通道档存储（纯内核测试需要自己存档）。"""
    return ProfileStore()


@pytest.fixture()
def default_store() -> ProfileStore:
    """预置 benchmark_faraday_2t 的存储。"""
    return make_default_store()


@pytest.fixture()
def app(default_store):
    application = create_app(default_store)
    application.config.update(TESTING=True)
    return application


@pytest.fixture()
def client(app):
    return app.test_client()
