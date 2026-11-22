# Xiaomi BE18000 board-2.bin

This local package installs the live Xiaomi BE18000 `board-2.bin` as a
rootfs overlay, so it overrides the generic QCN9274 board data without
an APK file-ownership conflict.

The binary is owner-supplied device data and is intentionally not
committed to this repository until its redistribution rights are
resolved.  Populate it before building:

```sh
cp QWRT/extracted/live-be18000/wifi/board-live-be18000.qcn9274 \
   package/firmware/ipq-wifi-xiaomi-be18000/files/board-2.bin
sha256sum package/firmware/ipq-wifi-xiaomi-be18000/files/board-2.bin
```

Expected size and hash:

```text
292256 bytes
0fcbb66e0a229bafc2bad9dd7cc8a5488134f4808673e73cd2808437849ab9e6
```

The archive contains:

| Variant | BDF | Length |
|---|---|---:|
| `Xiaomi_BE18000_live_1` | `bdwlan.b0001` | 63,488 |
| `Xiaomi_BE18000_live_2` | `bdwlan.b0002` | 100,352 |
| `Xiaomi_BE18000_live_4` | `bdwlan.b0004` | 102,400 |
| regdb key `bus=pci,qmi-chip-id=0,qmi-board-id=255` | live `regdb.bin` | 25,656 |
