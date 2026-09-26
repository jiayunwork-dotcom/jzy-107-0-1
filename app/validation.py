"""输入合法性拦截与通道参数数据结构。

所有计算入口都必须先经过这里的校验：非法输入在任何除法/扫描发生之前
就以 :class:`ValidationError` 挡回，并给出中文原因，避免扫描跑到某个点
才因除零等问题崩溃。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

# 扫描采样点数上限，防止调用方一次索取过量内存/CPU。
MIN_SCAN_POINTS = 2
MAX_SCAN_POINTS = 10_001

# 通道字段 -> 单位（错误消息里只给物理量名称，单位写在 README）。
_CHANNEL_FIELDS: dict[str, str] = {
    "magnetic_field": "磁感应强度 B",
    "electrode_spacing": "电极间距 d",
    "fluid_velocity": "流体速度 v",
    "conductivity": "流体电导率 σ",
    "cross_section": "通道截面积 A",
}


class ValidationError(ValueError):
    """带原因列表的非法输入错误，由 HTTP 层映射为 400。"""

    def __init__(self, reasons: str | list[str]):
        if isinstance(reasons, str):
            reasons = [reasons]
        self.reasons: list[str] = list(reasons)
        super().__init__("; ".join(self.reasons))


@dataclass(frozen=True)
class ChannelParams:
    """法拉第通道的几何与工质参数（经校验的不可变值对象）。"""

    magnetic_field: float       # B，特斯拉 T，>= 0
    electrode_spacing: float    # d，米 m，> 0
    fluid_velocity: float       # v，米每秒 m/s，>= 0
    conductivity: float         # σ，西门子每米 S/m，>= 0（允许 0）
    cross_section: float        # A，平方米 m²，> 0

    def to_dict(self) -> dict[str, float]:
        return {
            "magnetic_field": self.magnetic_field,
            "electrode_spacing": self.electrode_spacing,
            "fluid_velocity": self.fluid_velocity,
            "conductivity": self.conductivity,
            "cross_section": self.cross_section,
        }


def _is_finite_number(value: Any) -> bool:
    """只接受有限实数（int/float）。

    bool 是 int 的子类，必须显式排除；NaN 与无穷大一律拒绝。
    """
    if isinstance(value, bool):
        return False
    if not isinstance(value, (int, float)):
        return False
    return math.isfinite(float(value))


def require_mapping(payload: Any) -> dict[str, Any]:
    """确保请求体是 JSON 对象（映射），否则直接拒绝。"""
    if not isinstance(payload, dict):
        raise ValidationError("请求体必须是 JSON 对象")
    return payload


def parse_channel(data: dict[str, Any]) -> ChannelParams:
    """从映射中解析并校验五个通道参数，收集全部字段级错误后一次性返回。"""
    reasons: list[str] = []
    values: dict[str, float] = {}

    for key, label in _CHANNEL_FIELDS.items():
        if key not in data or data[key] is None:
            reasons.append(f"缺少通道参数：{label}（字段 {key}）")
            continue
        raw = data[key]
        if not _is_finite_number(raw):
            reasons.append(f"{label}（字段 {key}）必须是有限实数")
            continue
        values[key] = float(raw)

    if not reasons:
        b = values["magnetic_field"]
        d = values["electrode_spacing"]
        v = values["fluid_velocity"]
        sigma = values["conductivity"]
        area = values["cross_section"]

        if b < 0.0:
            reasons.append("磁感应强度 B 不能为负")
        if d <= 0.0:
            reasons.append("电极间距 d 必须为正")
        if v < 0.0:
            reasons.append("流体速度 v 不能为负")
        if sigma < 0.0:
            reasons.append("流体电导率 σ 不能为负")
        if area <= 0.0:
            reasons.append("通道截面积 A 必须为正")

    if reasons:
        raise ValidationError(reasons)

    return ChannelParams(
        magnetic_field=values["magnetic_field"],
        electrode_spacing=values["electrode_spacing"],
        fluid_velocity=values["fluid_velocity"],
        conductivity=values["conductivity"],
        cross_section=values["cross_section"],
    )


def validate_load(value: Any, *, field: str = "load_resistance",
                  label: str = "负载电阻") -> float:
    """校验负载电阻：必须是有限的非负实数。"""
    if not _is_finite_number(value):
        raise ValidationError(f"{label}（字段 {field}）必须是有限实数")
    load = float(value)
    if load < 0.0:
        raise ValidationError(f"{label}（字段 {field}）不能为负")
    return load


def validate_scan_range(data: dict[str, Any]) -> tuple[float, float, int]:
    """校验扫描请求的区间与采样密度。

    返回 ``(r_min, r_max, num_points)``；端点必须满足 ``0 <= r_min < r_max``，
    采样点数必须是 [MIN_SCAN_POINTS, MAX_SCAN_POINTS] 内的整数。
    """
    reasons: list[str] = []

    r_min = data.get("r_min")
    r_max = data.get("r_max")
    num_points = data.get("num_points")

    if not _is_finite_number(r_min):
        reasons.append("扫描下限 r_min 必须是有限实数")
    elif float(r_min) < 0.0:
        reasons.append("扫描下限 r_min 不能为负")

    if not _is_finite_number(r_max):
        reasons.append("扫描上限 r_max 必须是有限实数")

    # bool 是 int 的子类，num_points 必须是真正的整数。
    if isinstance(num_points, bool) or not isinstance(num_points, int):
        reasons.append(
            f"采样点数 num_points 必须是 {MIN_SCAN_POINTS}~{MAX_SCAN_POINTS} "
            "之间的整数"
        )
        num_points_valid = False
    else:
        num_points_valid = True

    if reasons:
        raise ValidationError(reasons)

    r_min_f = float(r_min)
    r_max_f = float(r_max)

    if r_max_f <= r_min_f:
        reasons.append("扫描上限 r_max 必须严格大于下限 r_min")
    if num_points_valid and num_points < MIN_SCAN_POINTS:
        reasons.append(f"采样点数不能少于 {MIN_SCAN_POINTS} 个")
    if num_points_valid and num_points > MAX_SCAN_POINTS:
        reasons.append(f"采样点数不能超过 {MAX_SCAN_POINTS} 个")

    if reasons:
        raise ValidationError(reasons)

    return r_min_f, r_max_f, int(num_points)


def validate_profile_name(name: Any) -> str:
    """校验通道档名字：非空、可见字符、长度受限。"""
    if not isinstance(name, str) or not name:
        raise ValidationError("通道档名字不能为空")
    name = name.strip()
    if not name:
        raise ValidationError("通道档名字不能只有空白字符")
    if len(name) > 64:
        raise ValidationError("通道档名字长度不能超过 64 个字符")
    if any(ch.isspace() and ch != " " for ch in name):
        # 允许普通空格，拒绝换行/制表符等，避免日志与路径类歧义。
        raise ValidationError("通道档名字不能包含换行或制表符")
    return name
