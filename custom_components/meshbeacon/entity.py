# SPDX-License-Identifier: Apache-2.0
"""Base entities. Everything belongs to one device, the MeshBeacon node."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .client import Peer
from .const import DOMAIN, MANUFACTURER
from .coordinator import MeshBeaconCoordinator
from .nodes import node_key


def node_id(coordinator: MeshBeaconCoordinator) -> str:
    """The stable prefix of this node's unique IDs; never the app's slug as such (nodes.py)."""
    return node_key(coordinator.config_entry)


def node_device(coordinator: MeshBeaconCoordinator) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, node_id(coordinator))},
        name="MeshBeacon",
        manufacturer=MANUFACTURER,
        model="Reticulum node",
        sw_version=coordinator.data.version if coordinator.data else None,
    )


class MeshBeaconEntity(CoordinatorEntity[MeshBeaconCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: MeshBeaconCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{node_id(coordinator)}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = node_device(coordinator)


class MeshBeaconPeerEntity(CoordinatorEntity[MeshBeaconCoordinator]):
    """An entity about one configured peer. Peers are not devices, so these belong to the node."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: MeshBeaconCoordinator, peer_name: str, key: str) -> None:
        super().__init__(coordinator)
        self.peer_name = peer_name
        self._attr_unique_id = f"{node_id(coordinator)}_peer_{peer_name.casefold()}_{key}"
        self._attr_translation_key = f"peer_{key}"
        self._attr_translation_placeholders = {"peer": peer_name}
        self._attr_device_info = node_device(coordinator)

    @property
    def peer(self) -> Peer | None:
        return self.coordinator.data.peer(self.peer_name) if self.coordinator.data else None

    @property
    def available(self) -> bool:
        return super().available and self.peer is not None
