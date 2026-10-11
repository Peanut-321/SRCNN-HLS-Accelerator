"""Read-only acceptance check for the repaired Q20.12 deployment IP ZIP."""

import argparse
import hashlib
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
import zipfile


EXPECTED_SHA256 = "ac79f070bd1a4fc3458617628802ae25855c5e106fbac14b9a01c916aceec965"
EXPECTED_BYTES = 498396
EXPECTED_NAME = "srcnn_axis_dataflow_top"


def inspect_package(path):
    if not path.is_file():
        raise ValueError(f"IP package not found: {path}")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != EXPECTED_SHA256 or path.stat().st_size != EXPECTED_BYTES:
        raise ValueError(
            f"Package does not match the approved export. Size={path.stat().st_size}; "
            f"SHA256={digest}. Do not integrate it until provenance is confirmed."
        )
    with zipfile.ZipFile(path) as archive:
        bad = archive.testzip()
        if bad:
            raise ValueError(f"ZIP integrity failure: {bad}")
        manifests = [n for n in archive.namelist() if n.split("/")[-1] == "component.xml"]
        if len(manifests) != 1:
            raise ValueError(f"Expected one component.xml, found {len(manifests)}")
        root = ET.fromstring(archive.read(manifests[0]))
        ns = {"s": "http://www.spiritconsortium.org/XMLSchema/SPIRIT/1685-2009"}
        name = root.findtext("s:name", namespaces=ns)
        if name != EXPECTED_NAME:
            raise ValueError(f"Unexpected IP name: {name}")
        interfaces = {
            item.findtext("s:name", namespaces=ns)
            for item in root.findall("s:busInterfaces/s:busInterface", ns)
        }
        required = {"input_r", "output_r", "m_axi_model_mem", "s_axi_control"}
        if not required <= interfaces:
            raise ValueError(f"Missing interfaces: {sorted(required - interfaces)}")
    print("PASS: Package identity, ZIP integrity and required interfaces verified.")
    print(f"Package: {path.resolve()}")
    print(f"SHA256: {digest}")
    print(f"Interfaces: {', '.join(sorted(interfaces))}")
    print("This check does not establish Vivado timing closure or board correctness.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    args = parser.parse_args()
    try:
        inspect_package(args.package)
    except (ValueError, OSError, zipfile.BadZipFile, ET.ParseError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
