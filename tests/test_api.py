"""HTTP 层端到端测试（Flask test client）。

覆盖：
- /compute 单点核算、/scan 扫描的接口行为与基准百伏回归；
- [锁死判据] HTTP 层单点功率与扫描同负载处一致；
- 非法输入在计算前被挡回（400，带原因），不会扫描中途崩掉；
- 扫描区间端点次序、采样密度的合理性校验；
- 通道档 CRUD 与“两套档同时扫描不串用”。
"""

from __future__ import annotations

import pytest

from app.profiles import BENCHMARK_PROFILE_NAME

CHANNEL = {
    "magnetic_field": 2.0,
    "electrode_spacing": 0.5,
    "fluid_velocity": 100.0,
    "conductivity": 10.0,
    "cross_section": 0.1,
}


def _post(client, path, payload):
    return client.post(path, json=payload)


# --------------------------------------------------------------------------- #
# 单点核算
# --------------------------------------------------------------------------- #

def test_compute_benchmark_matched_load(client):
    resp = _post(client, "/compute", {**CHANNEL, "load_resistance": 0.5})
    assert resp.status_code == 200
    body = resp.get_json()

    # [基准手算回归] 2 T × 0.5 m × 100 m/s = 100 V，百伏量级
    assert body["open_circuit_voltage"] == pytest.approx(100.0)
    assert body["internal_resistance"] == pytest.approx(0.5)
    assert body["current"] == pytest.approx(100.0)
    assert body["power"] == pytest.approx(5000.0)


def test_compute_short_circuit(client):
    resp = _post(client, "/compute", {**CHANNEL, "load_resistance": 0.0})
    body = resp.get_json()
    assert resp.status_code == 200
    assert body["current"] == pytest.approx(200.0)  # 短路电流，不是开路电压
    assert body["power"] == 0.0


def test_compute_zero_conductivity_returns_null_internal_resistance(client):
    payload = {**CHANNEL, "conductivity": 0.0, "load_resistance": 3.0}
    body = _post(client, "/compute", payload).get_json()
    assert body["internal_resistance"] is None
    assert body["current"] == 0.0
    assert body["power"] == 0.0


@pytest.mark.parametrize("field,bad", [
    ("magnetic_field", -2.0),
    ("electrode_spacing", 0.0),
    ("fluid_velocity", -1.0),
    ("conductivity", -0.5),
    ("cross_section", -0.1),
])
def test_compute_rejects_illegal_channel_inputs_with_reasons(client, field, bad):
    payload = {**CHANNEL, field: bad, "load_resistance": 1.0}
    resp = _post(client, "/compute", payload)
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["error"]
    assert body["reasons"]  # 必须说明原因


def test_compute_rejects_negative_load_before_scanning(client):
    resp = _post(client, "/compute", {**CHANNEL, "load_resistance": -0.2})
    assert resp.status_code == 400
    assert any("负载" in r for r in resp.get_json()["reasons"])


def test_compute_requires_channel_somehow(client):
    resp = _post(client, "/compute", {"load_resistance": 1.0})
    assert resp.status_code == 400


def test_compute_rejects_inline_and_profile_together(client):
    resp = _post(client, "/compute", {
        **CHANNEL, "profile": BENCHMARK_PROFILE_NAME, "load_resistance": 0.5,
    })
    assert resp.status_code == 400


def test_compute_unknown_profile_is_404(client):
    resp = _post(client, "/compute", {"profile": "ghost", "load_resistance": 1.0})
    assert resp.status_code == 404
    assert resp.get_json()["reasons"]


# --------------------------------------------------------------------------- #
# 扫描
# --------------------------------------------------------------------------- #

def test_scan_curve_shape_and_peak_at_internal_resistance(client):
    resp = _post(client, "/scan", {
        **CHANNEL, "r_min": 0.0, "r_max": 1.0, "num_points": 5,
    })
    assert resp.status_code == 200
    body = resp.get_json()

    assert body["optimal_load"] == pytest.approx(0.5)
    assert body["peak"]["index"] == 2
    assert body["peak"]["load_resistance"] == pytest.approx(0.5)
    assert body["peak"]["power"] == pytest.approx(5000.0)
    assert len(body["points"]) == 5
    # 端点在曲线上
    assert body["points"][0]["load_resistance"] == pytest.approx(0.0)
    assert body["points"][-1]["load_resistance"] == pytest.approx(1.0)
    # 2 倍内阻点功率低于峰值
    assert body["points"][4]["power"] < body["peak"]["power"]


def test_scan_single_point_consistency_over_http(client):
    # [锁死判据] 单点核算的功率必须等于扫描曲线同负载处的值。
    scan_body = _post(client, "/scan", {
        **CHANNEL, "r_min": 0.0, "r_max": 1.0, "num_points": 5,
    }).get_json()
    for point in scan_body["points"]:
        compute_body = _post(client, "/compute", {
            **CHANNEL, "load_resistance": point["load_resistance"],
        }).get_json()
        assert compute_body["power"] == pytest.approx(point["power"])
        assert compute_body["current"] == pytest.approx(point["current"])
        assert compute_body["open_circuit_voltage"] == pytest.approx(
            scan_body["open_circuit_voltage"]
        )


def test_scan_via_profile_name_matches_inline(client):
    inline = _post(client, "/scan", {
        **CHANNEL, "r_min": 0.0, "r_max": 1.0, "num_points": 5,
    }).get_json()
    named = _post(client, "/scan", {
        "profile": BENCHMARK_PROFILE_NAME,
        "r_min": 0.0, "r_max": 1.0, "num_points": 5,
    }).get_json()
    assert named["profile"] == BENCHMARK_PROFILE_NAME
    assert named["peak"] == inline["peak"]
    assert named["points"] == inline["points"]


def test_scan_zero_conductivity_curve_is_all_zero(client):
    body = _post(client, "/scan", {
        **CHANNEL, "conductivity": 0.0,
        "r_min": 0.0, "r_max": 5.0, "num_points": 6,
    }).get_json()
    assert body["optimal_load"] is None
    assert all(point["current"] == 0.0 for point in body["points"])
    assert all(point["power"] == 0.0 for point in body["points"])


def test_scan_rejects_reversed_range(client):
    resp = _post(client, "/scan", {
        **CHANNEL, "r_min": 1.0, "r_max": 0.0, "num_points": 5,
    })
    assert resp.status_code == 400
    assert any("r_max" in r for r in resp.get_json()["reasons"])


def test_scan_rejects_too_few_points(client):
    resp = _post(client, "/scan", {
        **CHANNEL, "r_min": 0.0, "r_max": 1.0, "num_points": 1,
    })
    assert resp.status_code == 400


def test_scan_rejects_non_integer_points(client):
    resp = _post(client, "/scan", {
        **CHANNEL, "r_min": 0.0, "r_max": 1.0, "num_points": 5.5,
    })
    assert resp.status_code == 400


def test_scan_density_is_observed(client):
    body = _post(client, "/scan", {
        **CHANNEL, "r_min": 0.0, "r_max": 2.0, "num_points": 201,
    }).get_json()
    assert len(body["points"]) == 201
    # 0.01 Ω 步长下，网格正好覆盖 R_i = 0.5 Ω
    assert body["peak"]["load_resistance"] == pytest.approx(0.5)


# --------------------------------------------------------------------------- #
# 通道档
# --------------------------------------------------------------------------- #

def test_profile_crud_over_http(client):
    listing = client.get("/profiles").get_json()
    assert any(p["name"] == BENCHMARK_PROFILE_NAME for p in listing["profiles"])

    rig = {"magnetic_field": 1.5, "electrode_spacing": 0.4,
           "fluid_velocity": 80.0, "conductivity": 8.0, "cross_section": 0.08}
    created = client.put("/profiles/lab-rig-1", json=rig)
    assert created.status_code == 200
    body = created.get_json()
    assert body["name"] == "lab-rig-1"
    assert body["open_circuit_voltage"] == pytest.approx(1.5 * 0.4 * 80.0)

    fetched = client.get("/profiles/lab-rig-1")
    assert fetched.status_code == 200
    assert fetched.get_json()["channel"]["magnetic_field"] == 1.5

    deleted = client.delete("/profiles/lab-rig-1")
    assert deleted.status_code == 200
    assert client.get("/profiles/lab-rig-1").status_code == 404


def test_put_profile_validates_before_saving(client):
    bad = {"magnetic_field": -1.0, "electrode_spacing": 0.4,
           "fluid_velocity": 80.0, "conductivity": 8.0, "cross_section": 0.08}
    resp = client.put("/profiles/bad-rig", json=bad)
    assert resp.status_code == 400
    assert client.get("/profiles/bad-rig").status_code == 404


def test_two_profiles_concurrent_scans_do_not_mix(client):
    rig_b = {"magnetic_field": 4.0, "electrode_spacing": 0.2,
             "fluid_velocity": 250.0, "conductivity": 5.0, "cross_section": 0.04}
    assert client.put("/profiles/rig-b", json=rig_b).status_code == 200

    scan_a = _post(client, "/scan", {
        "profile": BENCHMARK_PROFILE_NAME,
        "r_min": 0.0, "r_max": 2.0, "num_points": 401,
    }).get_json()
    scan_b = _post(client, "/scan", {
        "profile": "rig-b",
        "r_min": 0.0, "r_max": 2.0, "num_points": 401,
    }).get_json()

    # A 内阻 0.5 Ω，B 内阻 1.0 Ω，峰值必须各在各的位置
    assert scan_a["peak"]["load_resistance"] == pytest.approx(0.5, abs=0.01)
    assert scan_b["peak"]["load_resistance"] == pytest.approx(1.0, abs=0.01)
    assert scan_a["open_circuit_voltage"] == pytest.approx(100.0)
    assert scan_b["open_circuit_voltage"] == pytest.approx(4.0 * 0.2 * 250.0)


# --------------------------------------------------------------------------- #
# 协议层边角
# --------------------------------------------------------------------------- #

def test_non_json_body_is_rejected(client):
    resp = client.post("/compute", data="not-json", content_type="text/plain")
    assert resp.status_code == 400
    assert resp.get_json()["reasons"]


def test_unknown_route_returns_json_404(client):
    resp = client.get("/nope")
    assert resp.status_code == 404
    assert resp.is_json


def test_method_not_allowed_is_json(client):
    resp = client.get("/compute")
    assert resp.status_code == 405
    assert resp.is_json


def test_missing_json_body_is_rejected(client):
    resp = client.post("/compute", content_type="application/json")
    assert resp.status_code == 400
