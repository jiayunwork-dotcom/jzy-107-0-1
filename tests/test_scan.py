"""负载扫描测试。

锁死的核心判据：
1. 内阻确定时，功率曲线峰值必须落在负载等于内阻处；
2. 单点核算在某负载处的功率，必须与扫描曲线在同一负载处的值一致
   （扫描与单点共用 circuit.solve_load，这里用测试钉死）；
3. σ=0 时整条曲线电流、功率为零。
另含区间/采样密度的校验。
"""

from __future__ import annotations

import math

import pytest

from app.circuit import solve_load
from app.scan import linspace, scan_loads
from app.validation import ValidationError, validate_scan_range

V_OC = 100.0
R_I = 0.5


# [锁死判据] 峰值落在负载等于内阻处 ---------------------------------------- #

def test_power_curve_peaks_at_load_equal_internal_resistance():
    # 网格 0..1 Ω、5 个点，第 3 个点正好是 0.5 Ω = R_i。
    curve = scan_loads(V_OC, R_I, r_min=0.0, r_max=1.0, num_points=5)
    peak = curve.peak
    assert peak.load_resistance == pytest.approx(R_I)
    assert curve.optimal_load == R_I
    assert peak.power == pytest.approx(V_OC**2 / (4.0 * R_I))

    # 理论保证：对任何其它采样点，峰值功率都是严格最大的。
    for point in curve.points:
        assert point.power <= peak.power + 1e-12


def test_power_at_2ri_on_curve_is_below_peak():
    curve = scan_loads(V_OC, R_I, 0.0, 2.0 * R_I, num_points=3)
    loads = [point.load_resistance for point in curve.points]
    assert loads == pytest.approx([0.0, R_I, 2.0 * R_I])
    powers = {point.load_resistance: point.power for point in curve.points}
    assert powers[2.0 * R_I] < powers[R_I]
    assert curve.peak.load_resistance == pytest.approx(R_I)


def test_peak_for_different_internal_resistance_moves_with_it():
    # 换一档内阻，峰值跟着移动到新的 R_i（网格覆盖到它）。
    for r_i in (0.25, 1.0, 3.0):
        curve = scan_loads(V_OC, r_i, 0.0, 2.0 * r_i, num_points=5)
        assert curve.peak.load_resistance == pytest.approx(r_i)
        assert curve.optimal_load == r_i


# [锁死判据] 单点与扫描在同一负载处一致 ------------------------------------ #

@pytest.mark.parametrize("target_load", [0.0, 0.25, 0.5, 0.75, 1.0])
def test_single_point_matches_scan_at_same_load(target_load):
    curve = scan_loads(V_OC, R_I, r_min=0.0, r_max=1.0, num_points=5)
    on_curve = next(
        point for point in curve.points
        if point.load_resistance == pytest.approx(target_load)
    )
    single = solve_load(V_OC, R_I, target_load)
    assert on_curve.power == pytest.approx(single.power)
    assert on_curve.current == pytest.approx(single.current)


def test_scan_curve_uses_same_kernel_as_single_point_on_dense_grid():
    curve = scan_loads(V_OC, R_I, 0.01, 4.0, num_points=137)
    for point in curve.points:
        single = solve_load(V_OC, R_I, point.load_resistance)
        assert point.power == pytest.approx(single.power)
        assert point.current == pytest.approx(single.current)


# σ=0 边界 ----------------------------------------------------------------- #

def test_insulating_fluid_gives_flat_zero_curve():
    curve = scan_loads(V_OC, math.inf, 0.0, 10.0, num_points=21)
    assert curve.optimal_load is None
    assert all(point.current == 0.0 for point in curve.points)
    assert all(point.power == 0.0 for point in curve.points)
    assert curve.peak.power == 0.0
    assert curve.peak.load_resistance == pytest.approx(0.0)  # 并列取最左


# 网格工具与校验 ----------------------------------------------------------- #

def test_linspace_includes_endpoints_and_is_uniform():
    grid = linspace(0.0, 1.0, 5)
    assert grid[0] == 0.0
    assert grid[-1] == 1.0
    assert len(grid) == 5
    step = grid[1] - grid[0]
    for a, b in zip(grid, grid[1:]):
        assert b - a == pytest.approx(step)


def test_scan_range_validation_rejects_bad_endpoint_order():
    with pytest.raises(ValidationError) as exc:
        validate_scan_range({"r_min": 1.0, "r_max": 1.0, "num_points": 5})
    assert any("r_max" in reason for reason in exc.value.reasons)


def test_scan_range_validation_rejects_negative_min():
    with pytest.raises(ValidationError):
        validate_scan_range({"r_min": -0.1, "r_max": 1.0, "num_points": 5})


@pytest.mark.parametrize("bad_points", [0, 1, -3, 5.0, True, "10"])
def test_scan_range_validation_rejects_bad_point_counts(bad_points):
    with pytest.raises(ValidationError):
        validate_scan_range({"r_min": 0.0, "r_max": 1.0, "num_points": bad_points})


def test_scan_range_validation_rejects_excessive_point_count():
    with pytest.raises(ValidationError) as exc:
        validate_scan_range({"r_min": 0.0, "r_max": 1.0, "num_points": 10_002})
    assert any("超过" in reason for reason in exc.value.reasons)
