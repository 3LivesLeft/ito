>Understanding radio signal
A received signal reading is a clue, not a delivery guarantee.

RSSI describes received signal strength, commonly in dBm: a value closer to zero is stronger, so -90 dBm is stronger than -110 dBm. SNR compares signal with noise; a larger value generally means more margin above noise. Some LoRa signals can be decoded at negative SNR, depending on settings and conditions.
Readings usually describe what your device received, not what the other person received. Different transmit power, antennas, obstructions and interference can make the two directions perform differently. Multi-hop readings may describe only part of the route.
Compare repeated tests with the same settings and a known peer. A successful reply or delivery acknowledgement is more useful than a single signal reading.

`[Positioning a radio antenna`:/page/communications/antenna.mu]
`[How network relays work`:/page/communications/mesh.mu]

Reviewed: 2026-11-22
`[Communications`:/page/communications/index.mu]  `[Home`:/page/index.mu]
