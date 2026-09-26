"""法拉第式 MHD 通道电学性能核算服务应用包。"""

from __future__ import annotations

from flask import Flask

from .api import (
    api_bp,
    handle_method_not_allowed,
    handle_not_found,
)
from .profiles import ProfileStore, make_default_store


def create_app(store: ProfileStore | None = None) -> Flask:
    """Flask 应用工厂。

    Parameters
    ----------
    store:
        可选的通道档存储实例；不传则使用预置了基准通道档的默认存储。
        测试时可注入全新（空或预置）的存储以保证用例间隔离。
    """
    app = Flask(__name__)
    app.extensions["mhd_profile_store"] = (
        store if store is not None else make_default_store()
    )
    app.register_blueprint(api_bp)
    # 路由层 404/405 发生在蓝图派发之外，必须在应用层注册。
    app.register_error_handler(404, handle_not_found)
    app.register_error_handler(405, handle_method_not_allowed)
    return app


__all__ = ["create_app"]
