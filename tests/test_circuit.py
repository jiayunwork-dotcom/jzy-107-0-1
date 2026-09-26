"""单负载求解测试：电流、功率、短路/绝缘边界与基准手算值。"""

from __future__ import annotations

import math

import pytest

from app.circuit import solve_load

V_OC = 100.0   # V，基准档开路电压
R_I = 0.5      # Ω，基准档内阻


def test_matched_load_gives_half_voltage_and_max_power():
    # R_L = R_i：电流 = V_oc/(2 R_i) = 100 A，P = I²R = 5000 W
    out = solve_load(V_OC, R_I, R_I)
    assert out.current == pytest.approx(100.0)
    assert out.power == pytest.approx(5000.0)
    assert out.power == pytest.approx(V_OC**2 / (4.0 * R_I))


def test_short_circuit_current_is_not_open_circuit_voltage():
    # R_L = 0：电流是短路电流 V_oc/R_i（200 A），负载功率为 0；
    # 不能把短路电流和开路电压混为一谈。
    out = solve_load(V_OC, R_I, 0.0)
    assert out.current == pytest.approx(V_OC / R_I)
    assert out.power == 0.0


def test_power_at_double_internal_resistance_is_lower():
    # [锁死判据的一部分] R_L 从 R_i 改到 2R_i，提取功率必须下降。
    matched = solve_load(V_OC, R_I, R_I).power
    doubled = solve_load(V_OC, R_I, 2.0 * R_I).power
    assert doubled < matched
    # 解析值：V²·2R/(3R)² = 2/9 · V²/R ≈ 4444.4 W
    assert doubled == pytest.approx(2.0 / 9.0 * V_OC**2 / R_I, rel=1e-12)


def test_zero_conductivity_channel_yields_zero_current_and_power():
    # [锁死判据 3] σ=0 ⇒ R_i=∞ ⇒ I=0、P=0，任意负载都一样。
    for load in (0.0, R_I, 100.0):
        out = solve_load(V_OC, math.inf, load)
        assert out.current == 0.0
        assert out.power == 0.0
        assert math.isinf(out.internal_resistance)


def test_current_decreases_monotonically_with_load():
    currents = [solve_load(V_OC, R_I, rl).current for rl in (0.0, 0.5, 1.0, 10.0)]
    assert currents == sorted(currents, reverse=True)
    assert all(c > 0.0 for c in currents)
