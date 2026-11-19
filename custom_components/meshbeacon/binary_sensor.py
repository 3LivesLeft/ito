# SPDX-License-Identifier: Apache-2.0
"""Binary sensors: Reticulum running, transport mode, a problem flag, and per-peer connection."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorEntityDescription
from homeassistant.components.binary_sensor.const import BinarySensorDeviceClass
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .client import Status
from .coordinator import MeshBeaconConfigEntry, MeshBeaconCoordinator
from .entity import MeshBeaconEntity, MeshBeaconPeerEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class NodeBinarySensor(BinarySensorEntityDescription):
    value_fn: Callable[[Status], bool | None]


NODE_BINARY_SENSORS: tuple[NodeBinarySensor, ...] = (
    NodeBinarySensor(
        key="reticulum_running",
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.running,
    ),
    NodeBinarySensor(
        key="transport_mode",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.transport_enabled,
    ),
    NodeBinarySensor(
        key="problem_detected",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda s: s.problem != "none",
    ),
)


class MeshBeaconBinarySensor(MeshBeaconEntity, BinarySensorEntity):
    entity_description: NodeBinarySensor

    def __init__(self, coordinator: MeshBeaconCoordinator, description: NodeBinarySensor) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.value_fn(self.coordinator.data)


class MeshBeaconPeerConnected(MeshBeaconPeerEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: MeshBeaconCoordinator, peer: str) -> None:
        super().__init__(coordinator, peer, "connected")

    @property
    def is_on(self) -> bool | None:
        peer = self.peer
        return None if peer is None else peer.connected


async def async_setup_entry(
    hass: HomeAssistant, entry: MeshBeaconConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(MeshBeaconBinarySensor(coordinator, d) for d in NODE_BINARY_SENSORS)
    known: set[str] = set()

    @callback
    def add_peers() -> None:
        new = [p.name for p in coordinator.data.peers if p.name not in known] if coordinator.data else []
        known.update(new)
        async_add_entities(MeshBeaconPeerConnected(coordinator, name) for name in new)

    add_peers()
    entry.async_on_unload(coordinator.async_add_listener(add_peers))
