"""通道档存取：进程内命名通道几何/工质参数。

- 线程安全（一把可重入锁护住全部读写，扫描接口可能被并发调用）；
- 只在进程运行期间可靠存取，不跨重启保留，不做任何持久化；
- 两个通道档是互相独立的值对象，扫描时各取各的参数，不会算串。
"""

from __future__ import annotations

import threading

from .induction import open_circuit_voltage
from .validation import ChannelParams


class ProfileNotFound(KeyError):
    """通道档不存在，由 HTTP 层映射为 404。"""

    def __init__(self, name: str):
        self.name = name
        super().__init__(f"通道档不存在：{name}")


# 预置基准档：2 T 磁场、0.5 m 电极间距、100 m/s 流速、σ=10 S/m、A=0.1 m²。
# V_oc = 2×0.5×100 = 100 V；R_i = 0.5/(10×0.1) = 0.5 Ω。
BENCHMARK_PROFILE_NAME = "benchmark_faraday_2t"
BENCHMARK_CHANNEL = ChannelParams(
    magnetic_field=2.0,
    electrode_spacing=0.5,
    fluid_velocity=100.0,
    conductivity=10.0,
    cross_section=0.1,
)


class ProfileStore:
    """线程安全的内存通道档存储。"""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._profiles: dict[str, ChannelParams] = {}

    def save(self, name: str, channel: ChannelParams) -> None:
        """保存或覆盖一个通道档（放入的是不可变值对象的引用，之后互不影响）。"""
        with self._lock:
            self._profiles[name] = channel

    def get(self, name: str) -> ChannelParams:
        with self._lock:
            try:
                return self._profiles[name]
            except KeyError as exc:
                raise ProfileNotFound(name) from exc

    def delete(self, name: str) -> None:
        with self._lock:
            if name not in self._profiles:
                raise ProfileNotFound(name)
            del self._profiles[name]

    def names(self) -> list[str]:
        with self._lock:
            return sorted(self._profiles)

    def all(self) -> dict[str, ChannelParams]:
        with self._lock:
            return dict(self._profiles)

    def __contains__(self, name: object) -> bool:
        with self._lock:
            return name in self._profiles

    def __len__(self) -> int:
        with self._lock:
            return len(self._profiles)


def benchmark_summary(name: str, channel: ChannelParams) -> dict[str, object]:
    """通道档对外表示：回显参数并附带手算核对用的电压/内阻。"""
    return {
        "name": name,
        "channel": channel.to_dict(),
        "open_circuit_voltage": open_circuit_voltage(
            channel.magnetic_field,
            channel.electrode_spacing,
            channel.fluid_velocity,
        ),
    }


def make_default_store() -> ProfileStore:
    """预置基准通道档的默认存储（每次进程启动重建）。"""
    store = ProfileStore()
    store.save(BENCHMARK_PROFILE_NAME, BENCHMARK_CHANNEL)
    return store
