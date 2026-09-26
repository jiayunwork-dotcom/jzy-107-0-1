"""通道档存取测试：CRUD、缺档 404 语义、以及两套档扫描绝不串用。"""

from __future__ import annotations

import threading

import pytest

from app.profiles import (
    BENCHMARK_PROFILE_NAME,
    ProfileNotFound,
    ProfileStore,
    make_default_store,
)
from app.scan import scan_loads
from app.induction import channel_electrics
from app.validation import ChannelParams

RIG_A = ChannelParams(2.0, 0.5, 100.0, 10.0, 0.1)   # R_i = 0.5 Ω
RIG_B = ChannelParams(4.0, 0.2, 250.0, 5.0, 0.04)   # R_i = 1.0 Ω


def test_default_store_contains_benchmark_profile():
    store = make_default_store()
    assert BENCHMARK_PROFILE_NAME in store
    assert store.get(BENCHMARK_PROFILE_NAME) == RIG_A
    assert len(store) == 1


def test_save_get_delete_lifecycle(store):
    store.save("rig-a", RIG_A)
    assert store.get("rig-a") == RIG_A
    store.delete("rig-a")
    with pytest.raises(ProfileNotFound):
        store.get("rig-a")


def test_get_unknown_profile_raises_not_found(store):
    with pytest.raises(ProfileNotFound) as exc:
        store.get("ghost")
    assert exc.value.name == "ghost"


def test_delete_unknown_profile_raises(store):
    with pytest.raises(ProfileNotFound):
        store.delete("ghost")


def test_overwrite_replaces_old_values(store):
    store.save("rig", RIG_A)
    store.save("rig", RIG_B)
    assert store.get("rig") == RIG_B


def _curve_for(store: ProfileStore, name: str):
    channel = store.get(name)
    v_oc, r_i = channel_electrics(channel)
    return scan_loads(v_oc, r_i, 0.0, 2.0, 401)


def test_two_profiles_scanned_independently_do_not_mix(store):
    # 两套通道档同时被扫描，各归各的：峰值负载必须分别等于各自的内阻。
    store.save("rig-a", RIG_A)
    store.save("rig-b", RIG_B)

    curve_a = _curve_for(store, "rig-a")
    curve_b = _curve_for(store, "rig-b")

    _, r_a = channel_electrics(RIG_A)
    _, r_b = channel_electrics(RIG_B)
    assert r_a != r_b

    assert curve_a.peak.load_resistance == pytest.approx(r_a, abs=2.0 / 400)
    assert curve_b.peak.load_resistance == pytest.approx(r_b, abs=2.0 / 400)

    # 两条曲线本身不同（V_oc、峰值功率都不同），且互不引用对方参数。
    assert curve_a.open_circuit_voltage != curve_b.open_circuit_voltage
    assert curve_a.peak.power != curve_b.peak.power
    # 同负载点（如 0.5 Ω）上两套档算出的功率也应该不同。
    power_a_at_05 = curve_a.points[100].power
    power_b_at_05 = curve_b.points[100].power
    assert power_a_at_05 != pytest.approx(power_b_at_05)


def test_concurrent_scans_of_two_profiles_stay_isolated(store):
    store.save("rig-a", RIG_A)
    store.save("rig-b", RIG_B)
    results: dict[tuple[int, str], float] = {}
    errors: list[Exception] = []

    def worker(worker_id: int, name: str):
        try:
            for _ in range(20):
                curve = _curve_for(store, name)
                _, r_i = channel_electrics(store.get(name))
                # 每次扫描结果必须仍落在本档内阻附近
                assert abs(curve.peak.load_resistance - r_i) < 2.0 / 400
            results[(worker_id, name)] = curve.peak.load_resistance
        except Exception as exc:  # noqa: BLE001 - 测试中收集线程异常
            errors.append(exc)

    threads = [
        threading.Thread(target=worker, args=(i, "rig-a" if i % 2 == 0 else "rig-b"))
        for i in range(8)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors
    for (_, name), peak_load in results.items():
        _, r_i = channel_electrics(store.get(name))
        assert peak_load == pytest.approx(r_i, abs=2.0 / 400)
