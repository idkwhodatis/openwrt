# SPDX-License-Identifier: GPL-2.0-only
#
# Local board-2.bin for the owner's hardware-converted BE10000, which the
# running QWRT identifies as xiaomi,be18000.  The archive contains the three
# live BDFs and the live regdb:
#
#   variant=Xiaomi_BE18000_live_1 -> bdwlan.b0001 (2.4 GHz,  63,488 B)
#   variant=Xiaomi_BE18000_live_2 -> bdwlan.b0002 (5 GHz,   100,352 B)
#   variant=Xiaomi_BE18000_live_4 -> bdwlan.b0004 (6 GHz,   102,400 B)
#   regdb                         -> live regdb.bin (25,656 B)
#
# SHA-256 of files/board-2.bin:
#   0fcbb66e0a229bafc2bad9dd7cc8a5488134f4808673e73cd2808437849ab9e6
#
# The BDFs are owner-supplied device data.  Resolve redistribution rights
# before publishing them; keep this package local to the porting tree until
# that is done.

include $(TOPDIR)/rules.mk

PKG_NAME:=ipq-wifi-xiaomi_be18000
PKG_RELEASE:=1

PKG_MAINTAINER:=OpenWrt BE18000 port
PKG_LICENSE:=Proprietary
PKGARCH:=all

include $(INCLUDE_DIR)/package.mk

define Build/Compile
endef

define Package/ipq-wifi-xiaomi_be18000
  SECTION:=firmware
  CATEGORY:=Firmware
  DEPENDS:=@TARGET_qualcommbe
  TITLE:=board-2.bin override for Xiaomi BE18000
endef

define Package/ipq-wifi-xiaomi_be18000/description
Installs the live Xiaomi BE18000 board-2.bin (2.4/5/6 GHz BDFs and regdb)
over the generic ath12k QCN9274 board data.  Use only on the BE18000.
endef

define Package/ipq-wifi-xiaomi_be18000/install
endef

define Package/ipq-wifi-xiaomi_be18000/install-overlay
	$(INSTALL_DIR) $(1)/lib/firmware/ath12k/QCN9274/hw2.0
	$(INSTALL_DATA) ./files/board-2.bin \
		$(1)/lib/firmware/ath12k/QCN9274/hw2.0/board-2.bin
endef

$(eval $(call BuildPackage,ipq-wifi-xiaomi_be18000))
