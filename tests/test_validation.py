"""输入合法性拦截测试：非法值必须在计算前挡回并给出原因。"""

from __future__ import annotations

import math

import pytest

from app.validation import (
    ChannelParams,
    ValidationError,
    parse_channel,
    validate_load,
    validate_profile_name,
)

VALID = {
    "magnetic_field": 2.0,
    "electrode_spacing": 0.5,
    "fluid_velocity": 100.0,
    "conductivity": 10.0,
    "cross_section": 0.1,
}


def test_valid_channel_parses():
    channel = parse_channel(dict(VALID))
    assert isinstance(channel, ChannelParams)
    assert channel.conductivity == 10.0


@pytest.mark.parametrize("field,bad_value,reason_kw", [
    ("magnetic_field", -1.0, "磁感应强度"),
    ("electrode_spacing", 0.0, "电极间距"),
    ("fluid_velocity", -5.0, "流体速度"),
    ("conductivity", -0.01, "电导率"),
    ("cross_section", -2.0, "截面积"),
])
def test_illegal_physics_values_are_rejected(field, bad_value, reason_kw):
    data = dict(VALID, **{field: bad_value})
    with pytest.raises(ValidationError) as exc:
        parse_channel(data)
    assert any(reason_kw in reason for reason in exc.value.reasons)


def test_zero_electrode_spacing_and_cross_section_rejected():
    with pytest.raises(ValidationError) as exc:
        parse_channel(dict(VALID, electrode_spacing=0.0, cross_section=0.0))
    # 多个字段的原因要一起收集，而不是撞到第一个就抛
    joined = " ".join(exc.value.reasons)
    assert "电极间距" in joined
    assert "截面积" in joined


def test_zero_conductivity_is_allowed():
    # 电导率为零是合法物理情形（绝缘工质），由计算内核返回 R_i=∞。
    channel = parse_channel(dict(VALID, conductivity=0.0))
    assert channel.conductivity == 0.0


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf"), "x", None])
def test_non_finite_or_non_numeric_fields_rejected(bad):
    with pytest.raises(ValidationError):
        parse_channel(dict(VALID, magnetic_field=bad))


def test_boolean_is_not_a_number():
    with pytest.raises(ValidationError):
        parse_channel(dict(VALID, magnetic_field=True))


def test_missing_fields_are_all_reported():
    with pytest.raises(ValidationError) as exc:
        parse_channel({})
    assert len(exc.value.reasons) == 5


def test_negative_load_rejected_before_any_computation():
    with pytest.raises(ValidationError) as exc:
        validate_load(-0.001)
    assert "负载" in exc.value.reasons[0]


@pytest.mark.parametrize("bad", [-1.0, float("nan"), float("inf"), "1"])
def test_load_must_be_finite_nonnegative(bad):
    with pytest.raises(ValidationError):
        validate_load(bad)


def test_profile_name_validation():
    assert validate_profile_name("lab-rig_1") == "lab-rig_1"
    assert validate_profile_name("  spaced  ") == "spaced"
    for bad in ("", "   ", "a\tb", "a\nb"):
        with pytest.raises(ValidationError):
            validate_profile_name(bad)
    with pytest.raises(ValidationError):
        validate_profile_name("x" * 65)


def test_reasons_are_human_readable():
    # 挡回时必须带原因，而不是光秃秃的 ValueError
    with pytest.raises(ValidationError) as exc:
        parse_channel(dict(VALID, magnetic_field=math.nan))
    assert exc.value.reasons and all(isinstance(r, str) for r in exc.value.reasons)
