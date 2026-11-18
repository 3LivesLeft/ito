# SPDX-License-Identifier: Apache-2.0
"""Sensors. State classes are chosen so that Home Assistant's own recorder keeps history and
long-term statistics; MeshBeacon stores none itself."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TypedDict

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfDataRate, UnitOfInformation
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from .client import Peer, Status
from .const import CONNECTIVITY, PROBLEMS, STATES
from .coordinator import MeshBeaconConfigEntry, MeshBeaconCoordinator
from .entity import MeshBeaconEntity, MeshBeaconPeerEntity

PARALLEL_UPDATES = 0  # all entities share one coordinator request

type Value = StateType | datetime


def _ts(value: float | None) -> datetime | None:
    return None if value is None else datetime.fromtimestamp(value, UTC)


@dataclass(frozen=True, kw_only=True)
class NodeSensor(SensorEntityDescription):
    value_fn: Callable[[Status], Value]


@dataclass(frozen=True, kw_only=True)
class PeerSensor(SensorEntityDescription):
    value_fn: Callable[[Peer], Value]


class Options(TypedDict, total=False):
    device_class: SensorDeviceClass
    native_unit_of_measurement: str
    suggested_unit_of_measurement: str
    suggested_display_precision: int
    state_class: SensorStateClass
    entity_category: EntityCategory


BYTES: Options = {
    "device_class": SensorDeviceClass.DATA_SIZE,
    "native_unit_of_measurement": UnitOfInformation.BYTES,
    "suggested_unit_of_measurement": UnitOfInformation.MEGABYTES,
    "state_class": SensorStateClass.TOTAL_INCREASING,
}
RATE: Options = {
    "device_class": SensorDeviceClass.DATA_RATE,
    "native_unit_of_measurement": UnitOfDataRate.BYTES_PER_SECOND,
    "suggested_unit_of_measurement": UnitOfDataRate.KILOBYTES_PER_SECOND,
    "state_class": SensorStateClass.MEASUREMENT,
}
MEMORY: Options = {
    "device_class": SensorDeviceClass.DATA_SIZE,
    "native_unit_of_measurement": UnitOfInformation.BYTES,
    "suggested_unit_of_measurement": UnitOfInformation.MEBIBYTES,
    "suggested_display_precision": 1,
    "state_class": SensorStateClass.MEASUREMENT,
    "entity_category": EntityCategory.DIAGNOSTIC,
}
COUNT: Options = {"state_class": SensorStateClass.TOTAL_INCREASING}
GAUGE: Options = {"state_class": SensorStateClass.MEASUREMENT}
DIAG: Options = {"entity_category": EntityCategory.DIAGNOSTIC}
TIMESTAMP: Options = {"device_class": SensorDeviceClass.TIMESTAMP}


def merge(*parts: Options) -> Options:
    merged: Options = {}
    for part in parts:
        merged.update(part)
    return merged


NODE_SENSORS: tuple[NodeSensor, ...] = (
    NodeSensor(key="status", device_class=SensorDeviceClass.ENUM, options=list(STATES), value_fn=lambda s: s.state),
    NodeSensor(
        key="connectivity",
        device_class=SensorDeviceClass.ENUM,
        options=list(CONNECTIVITY),
        value_fn=lambda s: s.connectivity,
    ),
    NodeSensor(
        key="problem",
        device_class=SensorDeviceClass.ENUM,
        options=list(PROBLEMS),
        value_fn=lambda s: s.problem,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    NodeSensor(key="app_started", value_fn=lambda s: _ts(s.app_started_at), **merge(TIMESTAMP, DIAG)),
    NodeSensor(key="reticulum_started", value_fn=lambda s: _ts(s.reticulum_started_at), **merge(TIMESTAMP, DIAG)),
    NodeSensor(key="peers_connected", value_fn=lambda s: s.peers_connected, **GAUGE),
    NodeSensor(key="peers_configured", value_fn=lambda s: s.peers_configured, **merge(GAUGE, DIAG)),
    NodeSensor(key="received", value_fn=lambda s: s.rx_bytes, **BYTES),
    NodeSensor(key="sent", value_fn=lambda s: s.tx_bytes, **BYTES),
    NodeSensor(key="receive_rate", value_fn=lambda s: s.rx_rate, **RATE),
    NodeSensor(key="send_rate", value_fn=lambda s: s.tx_rate, **RATE),
    NodeSensor(key="packets_received", value_fn=lambda s: s.packets_rx, **merge(COUNT, DIAG)),
    NodeSensor(key="packets_sent", value_fn=lambda s: s.packets_tx, **merge(COUNT, DIAG)),
    NodeSensor(key="known_paths", value_fn=lambda s: s.paths, **GAUGE),
    NodeSensor(key="relayed_links", value_fn=lambda s: s.relayed_links, **GAUGE),
    NodeSensor(key="announces_received", value_fn=lambda s: s.announces_rx, **merge(COUNT, DIAG)),
    NodeSensor(key="announces_sent", value_fn=lambda s: s.announces_tx, **merge(COUNT, DIAG)),
    NodeSensor(key="memory", value_fn=lambda s: s.memory_bytes, **MEMORY),
    NodeSensor(
        key="core_memory", value_fn=lambda s: s.core_memory_bytes, entity_registry_enabled_default=False, **MEMORY
    ),
    NodeSensor(
        key="reticulum_memory",
        value_fn=lambda s: s.reticulum_memory_bytes,
        entity_registry_enabled_default=False,
        **MEMORY,
    ),
    NodeSensor(
        key="cpu",
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=1,
        value_fn=lambda s: s.cpu_percent,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    NodeSensor(key="restarts", value_fn=lambda s: s.restarts, **merge(COUNT, DIAG)),
    NodeSensor(key="memory_restarts", value_fn=lambda s: s.memory_restarts, **merge(COUNT, DIAG)),
)

PEER_SENSORS: tuple[PeerSensor, ...] = (
    PeerSensor(key="connected_since", value_fn=lambda p: _ts(p.connected_since), **TIMESTAMP),
    PeerSensor(key="received", value_fn=lambda p: p.rx_bytes, **BYTES),
    PeerSensor(key="sent", value_fn=lambda p: p.tx_bytes, **BYTES),
    PeerSensor(key="receive_rate", value_fn=lambda p: p.rx_rate, **merge(RATE, DIAG)),
    PeerSensor(key="send_rate", value_fn=lambda p: p.tx_rate, **merge(RATE, DIAG)),
    PeerSensor(key="announces_received", value_fn=lambda p: p.announces_rx, **merge(COUNT, DIAG)),
    PeerSensor(key="announces_sent", value_fn=lambda p: p.announces_tx, **merge(COUNT, DIAG)),
    PeerSensor(key="reconnections", value_fn=lambda p: p.reconnections, **merge(COUNT, DIAG)),
)


class MeshBeaconSensor(MeshBeaconEntity, SensorEntity):
    entity_description: NodeSensor

    def __init__(self, coordinator: MeshBeaconCoordinator, description: NodeSensor) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Value:
        return self.entity_description.value_fn(self.coordinator.data)


class MeshBeaconPeerSensor(MeshBeaconPeerEntity, SensorEntity):
    entity_description: PeerSensor

    def __init__(self, coordinator: MeshBeaconCoordinator, peer: str, description: PeerSensor) -> None:
        super().__init__(coordinator, peer, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Value:
        peer = self.peer
        return None if peer is None else self.entity_description.value_fn(peer)


async def async_setup_entry(
    hass: HomeAssistant, entry: MeshBeaconConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(MeshBeaconSensor(coordinator, d) for d in NODE_SENSORS)
    known: set[str] = set()

    @callback
    def add_peers() -> None:
        new = [p.name for p in coordinator.data.peers if p.name not in known] if coordinator.data else []
        known.update(new)
        async_add_entities(MeshBeaconPeerSensor(coordinator, name, d) for name in new for d in PEER_SENSORS)

    add_peers()
    entry.async_on_unload(coordinator.async_add_listener(add_peers))
