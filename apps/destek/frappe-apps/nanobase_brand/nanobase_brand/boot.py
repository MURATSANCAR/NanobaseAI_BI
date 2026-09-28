import os


def extend(bootinfo):
	# «Hakkında» penceresinde gösterilen kod sürümü (imaj derlenirken verilir).
	bootinfo.nanobase_version = (os.environ.get("DESTEK_CODE_VERSION") or "")[:8]
