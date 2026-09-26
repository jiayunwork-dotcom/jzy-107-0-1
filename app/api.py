"""薄 HTTP 层：只做请求收发、参数解析与调度。

感应公式（B·d·v、d/σA）、负载求解与扫描循环全部位于 induction /
circuit / scan 模块，本文件不堆任何计算内核。

通道来源二选一：请求体内联五个通道字段，或用 ``profile`` 引用已保存的
通道档。
"""

from __future__ import annotations

import math
from typing import Any

from flask import Blueprint, current_app, jsonify, request

from .circuit import solve_load
from .induction import channel_electrics
from .profiles import ProfileNotFound, ProfileStore, benchmark_summary
from .scan import PowerCurve, scan_loads
from .validation import (
    ChannelParams,
    ValidationError,
    parse_channel,
    require_mapping,
    validate_load,
    validate_profile_name,
    validate_scan_range,
)

api_bp = Blueprint("mhd_api", __name__)


# --------------------------------------------------------------------------- #
# 辅助
# --------------------------------------------------------------------------- #

def _store() -> ProfileStore:
    return current_app.extensions["mhd_profile_store"]


def _json_body() -> dict[str, Any]:
    """取 JSON 请求体；Content-Type 不对或体不是对象时给带原因的 400。"""
    if not request.is_json:
        raise ValidationError("请求必须带 JSON 体（Content-Type: application/json）")
    data = request.get_json(silent=True)
    return require_mapping(data)


def _resolve_channel(data: dict[str, Any]) -> tuple[ChannelParams, str | None]:
    """解析通道来源：``profile`` 引用或内联字段，二选一，不能都给也不能都不给。"""
    profile_ref = data.get("profile")
    has_inline = any(key in data for key in (
        "magnetic_field", "electrode_spacing", "fluid_velocity",
        "conductivity", "cross_section",
    ))

    if profile_ref is not None and has_inline:
        raise ValidationError("profile 与内联通道参数不能同时提供，请二选一")

    if profile_ref is not None:
        name = validate_profile_name(profile_ref)
        return _store().get(name), name

    if has_inline:
        return parse_channel(data), None

    raise ValidationError(
        "必须提供通道参数：内联给出五个通道字段，或用 profile 引用通道档"
    )


def _finite_or_none(value: float) -> float | None:
    """JSON 不能表达 ±∞：内阻无穷时序列化为 null。"""
    return None if math.isinf(value) else value


def _error(message: str, reasons: list[str] | None = None, status: int = 400):
    payload: dict[str, Any] = {"error": message}
    if reasons:
        payload["reasons"] = reasons
    return jsonify(payload), status


def _curve_to_dict(curve: PowerCurve, channel: ChannelParams,
                   profile: str | None) -> dict[str, Any]:
    peak = curve.peak
    return {
        "channel": channel.to_dict(),
        "profile": profile,
        "open_circuit_voltage": curve.open_circuit_voltage,
        "internal_resistance": _finite_or_none(curve.internal_resistance),
        "r_min": curve.r_min,
        "r_max": curve.r_max,
        "num_points": curve.num_points,
        "optimal_load": curve.optimal_load,
        "peak": {
            "index": curve.points.index(peak),
            "load_resistance": peak.load_resistance,
            "current": peak.current,
            "power": peak.power,
        },
        "points": [
            {
                "load_resistance": point.load_resistance,
                "current": point.current,
                "power": point.power,
            }
            for point in curve.points
        ],
    }


# --------------------------------------------------------------------------- #
# 计算接口
# --------------------------------------------------------------------------- #

@api_bp.post("/compute")
def compute():
    """单点核算：给定一个负载电阻，返回电流与负载功率。"""
    data = _json_body()
    channel, profile = _resolve_channel(data)

    if "load_resistance" not in data or data["load_resistance"] is None:
        raise ValidationError("缺少负载电阻（字段 load_resistance，单位 Ω）")
    load = validate_load(data["load_resistance"])

    v_oc, r_i = channel_electrics(channel)
    solution = solve_load(v_oc, r_i, load)

    return jsonify({
        "channel": channel.to_dict(),
        "profile": profile,
        "open_circuit_voltage": solution.open_circuit_voltage,
        "internal_resistance": _finite_or_none(solution.internal_resistance),
        "load_resistance": solution.load_resistance,
        "current": solution.current,
        "power": solution.power,
    })


@api_bp.post("/scan")
def scan():
    """对负载区间 [r_min, r_max] 等间距扫描，给功率曲线并标出峰值。"""
    data = _json_body()
    channel, profile = _resolve_channel(data)
    r_min, r_max, num_points = validate_scan_range(data)

    v_oc, r_i = channel_electrics(channel)
    curve = scan_loads(v_oc, r_i, r_min, r_max, num_points)
    return jsonify(_curve_to_dict(curve, channel, profile))


# --------------------------------------------------------------------------- #
# 通道档接口
# --------------------------------------------------------------------------- #

@api_bp.get("/profiles")
def list_profiles():
    store = _store()
    return jsonify({
        "profiles": [
            benchmark_summary(name, channel)
            for name, channel in store.all().items()
        ]
    })


@api_bp.get("/profiles/<name>")
def get_profile(name: str):
    name = validate_profile_name(name)
    channel = _store().get(name)
    return jsonify(benchmark_summary(name, channel))


@api_bp.put("/profiles/<name>")
def put_profile(name: str):
    name = validate_profile_name(name)
    data = _json_body()
    channel = parse_channel(data)
    _store().save(name, channel)
    return jsonify(benchmark_summary(name, channel))


@api_bp.delete("/profiles/<name>")
def delete_profile(name: str):
    name = validate_profile_name(name)
    _store().delete(name)
    return jsonify({"deleted": name})


# --------------------------------------------------------------------------- #
# 错误处理
# --------------------------------------------------------------------------- #

@api_bp.errorhandler(ValidationError)
def handle_validation_error(exc: ValidationError):
    return _error("输入不合法", exc.reasons, 400)


@api_bp.errorhandler(ProfileNotFound)
def handle_profile_not_found(exc: ProfileNotFound):
    return _error("通道档不存在", [f"找不到名为 {exc.name!r} 的通道档"], 404)


def handle_not_found(_exc):
    # 路由层 404 发生在进入蓝图之前，需在应用层注册（见 create_app）。
    return _error("接口不存在", [f"路径 {request.path} 没有对应的处理函数"], 404)


def handle_method_not_allowed(_exc):
    return _error("方法不允许", [f"{request.method} 不支持用于该路径"], 405)
