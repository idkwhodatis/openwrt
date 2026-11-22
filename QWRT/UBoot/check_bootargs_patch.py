import glob, gzip, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import compare_fit as C

factory = glob.glob(os.path.join(C.BUILD, "*-squashfs-factory.ubi"))[0]
vols, names, _ = C.ubi_volumes(factory)
kid = next(k for k, v in names.items() if v == "kernel")
raw = b"".join(vols[kid][i] for i in sorted(vols[kid]))
root, total = C.parse_fdt(raw)
images = C.child(root, "images")
knode = next(c for c in images["children"] if c["name"].startswith("kernel"))
data = knode["props"]["data"]
print("FIT kernel image bytes", len(data), "compression", C.text(knode, "compression"))
kern = gzip.decompress(data)
print("decompressed kernel bytes", len(kern))
for needle in (b"bootargs-append", b"mangle_bootargs", b"root=/dev/ubiblock"):
    print(needle.decode(), "->", kern.find(needle))
# Linux version banner
i = kern.find(b"Linux version ")
print(kern[i:i+90].decode("latin1") if i >= 0 else "no version banner")
