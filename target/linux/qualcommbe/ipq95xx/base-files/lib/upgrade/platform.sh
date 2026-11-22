PART_NAME=firmware
REQUIRE_IMAGE_METADATA=1

RAMFS_COPY_BIN='fw_printenv fw_setenv head cmp sha256sum tr mktemp ubiformat ubiattach ubidetach ubimkvol ubirmvol ubinfo nanddump mtd'
RAMFS_COPY_DATA='/etc/fw_env.config /var/lock/fw_printenv.lock'

be18000_check_sysupgrade() {
	local image="$1"
	local board_dir="sysupgrade-xiaomi_be18000"
	local cmd members member dirs

	# The generated sysupgrade image is an uncompressed or gzip tar.
	# A raw factory.ubi has the UBI magic and must never reach
	# nand_do_upgrade: it is a ubiformat recovery image.
	cmd="$(identify_if_gzip "$image")cat"
	members="$($cmd < "$image" 2>/dev/null | tar tf - 2>/dev/null)" || {
		echo "BE18000: expected a sysupgrade tar, not a raw recovery image" >&2
		return 1
	}

	# nand_upgrade_tar uses the first sysupgrade-*/ directory.  Refuse
	# ambiguous archives so a differently named directory cannot be
	# selected instead of the Xiaomi one.
	dirs="$(printf '%s\n' "$members" | grep '^sysupgrade-[^/]*/$' | sort -u)"
	[ "$dirs" = "$board_dir/" ] || {
		echo "BE18000: expected exactly one $board_dir/ directory" >&2
		return 1
	}

	for member in CONTROL kernel root; do
		printf '%s\n' "$members" | grep -qx "$board_dir/$member" || {
			echo "BE18000: missing $board_dir/$member" >&2
			return 1
		}
	done

	[ "$($cmd < "$image" | tar xOf - "$board_dir/CONTROL" 2>/dev/null | wc -c)" -gt 0 ] || {
		echo "BE18000: empty $board_dir/CONTROL" >&2
		return 1
	}

	[ "$(identify_tar "$image" "$cmd" "$board_dir/kernel")" = "fit" ] || {
		echo "BE18000: kernel is not a FIT image" >&2
		return 1
	}

	[ "$(identify_tar "$image" "$cmd" "$board_dir/root")" = "squashfs" ] || {
		echo "BE18000: root is not a squashfs image" >&2
		return 1
	}

	return 0
}

platform_check_image() {
	case "$(board_name)" in
	linksys,ln6001)
		ln6001_preflight "$1" || {
			echo "LN6001 A/B preflight failed" >&2
			return 1
		}
		return 0
		;;
	xiaomi,be18000)
		# Only a correctly named sysupgrade tar with a non-empty
		# CONTROL, FIT kernel and squashfs root may be dispatched to
		# NAND.  Return 74 so --force cannot bypass this format check.
		nand_do_platform_check "$(board_name)" "$1" || return 74
		be18000_check_sysupgrade "$1" || return 74
		return 0
		;;
	*)
		return 0
		;;
	esac
}

platform_do_upgrade() {
	case "$(board_name)" in
	8devices,kiwi-dvk)
		CI_KERNPART="0:HLOS"
		CI_ROOTPART="rootfs"
		emmc_do_upgrade "$1"
		;;
	askey,sbe1v1k)
		CI_KERNPART="0:HLOS"
		CI_ROOTPART="rootfs"
		CI_DATAPART="rootfs_data"
		emmc_do_upgrade "$1"
		;;
	linksys,ln6001)
		ln6001_do_upgrade "$1" || return 1
		;;
	xiaomi,be18000)
		CI_KERNPART="kernel"
		CI_ROOTPART="rootfs"
		CI_DATAPART="rootfs_data"
		nand_do_upgrade "$1"
		;;
	*)
		default_do_upgrade "$1"
		;;
	esac
}

platform_copy_config() {
	case "$(board_name)" in
	8devices,kiwi-dvk|\
	askey,sbe1v1k)
		emmc_copy_config
		;;
	esac
}
