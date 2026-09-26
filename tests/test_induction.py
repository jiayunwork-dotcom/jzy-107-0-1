"""感应内核测试。

锁定判据：
- 磁感应强度翻倍，开路电压翻倍；
- 流体速度单独翻倍，开路电压同样翻倍；
- 内阻 R_i = d/(σA)，σ→0 时趋于无穷。
"""

from __future__ import annotations

import math

import pytest

from app.induction import channel_electrics, internal_resistance, open_circuit_voltage
from app.profiles import BENCHMARK_CHANNEL
from app.validation import ChannelParams
B, D, V, SIGMA, A = 2.0, 0.5, 100.0, 10.0, 0.1


def channel(**overrides) -> ChannelParams:
    base = dict(
        magnetic_field=B, electrode_spacing=D, fluid_velocity=V,
        conductivity=SIGMA, cross_section=A,
    )
    base.update(overrides)
    return ChannelParams(**base)


# [锁死判据 1] 磁感应强度翻倍 ⇒ 开路电压翻倍 ------------------------------- #

def test_open_circuit_voltage_doubles_with_magnetic_field():
    v1 = open_circuit_voltage(B, D, V)
    v2 = open_circuit_voltage(2 * B, D, V)
    assert v1 == B * D * V
    assert v2 == 2.0 * v1


@pytest.mark.parametrize("factor", [0.5, 1.0, 3.0, 10.0])
def test_open_circuit_voltage_linear_in_b(factor):
    # V_oc 对 B 是线性的，不只是翻倍一个点
    assert open_circuit_voltage(factor * B, D, V) == pytest.approx(
        factor * open_circuit_voltage(B, D, V)
    )


# [锁死判据 2] 流体速度翻倍 ⇒ 开路电压翻倍 --------------------------------- #

def test_open_circuit_voltage_doubles_with_velocity():
    v1 = open_circuit_voltage(B, D, V)
    v2 = open_circuit_voltage(B, D, 2 * V)
    assert v2 == 2.0 * v1


def test_zero_velocity_gives_zero_voltage():
    assert open_circuit_voltage(B, D, 0.0) == 0.0


def test_zero_field_gives_zero_voltage():
    assert open_circuit_voltage(0.0, D, V) == 0.0


# 内阻 --------------------------------------------------------------------- #

def test_internal_resistance_formula():
    # d/(σA) = 0.5/(10×0.1) = 0.5 Ω
    assert internal_resistance(D, SIGMA, A) == pytest.approx(0.5)


def test_internal_resistance_inverse_in_conductivity():
    r1 = internal_resistance(D, SIGMA, A)
    r2 = internal_resistance(D, SIGMA / 2.0, A)
    assert r2 == pytest.approx(2.0 * r1)


def test_zero_conductivity_means_infinite_internal_resistance():
    r_i = internal_resistance(D, 0.0, A)
    assert math.isinf(r_i)
    assert r_i > 0.0


def test_channel_electrics_benchmark_values():
    v_oc, r_i = channel_electrics(BENCHMARK_CHANNEL)
    # 2 T × 0.5 m × 100 m/s = 100 V
    assert v_oc == pytest.approx(100.0)
    assert r_i == pytest.approx(0.5)
