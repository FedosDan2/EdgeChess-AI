"""Download pinned official Stockfish 19 binaries; never run foreign binaries.

Keep the complete upstream distribution with sources and GPL notices alongside
the executable. Checksums are from the official sf_19 GitHub release assets.
"""

import argparse
import hashlib
import json
from pathlib import Path
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
ASSETS = {
    "x86_64": ("x86-64", "9defc0d4e55d49c65a6d042f3e571a39fcea499ade6dbe741b53b8c65e03611f"),
    "aarch64": ("arm64", "fe26cfd1d9db4c8af3d21e24d9ff34cacb31c1f940085a7583da11796f2bac01"),
}


def download(arch, output):
    target, digest = ASSETS[arch]
    directory = output / arch
    directory.mkdir(parents=True, exist_ok=True)
    archive = directory / "upstream.tar.gz"
    url = f"https://github.com/official-stockfish/Stockfish/releases/download/sf_19/stockfish-linux-{target}-universal.tar.gz"
    if not archive.exists():
        temporary = directory / "download.part"
        request = urllib.request.Request(url, headers={"User-Agent": "EdgeChess"})
        with urllib.request.urlopen(request, timeout=120) as response, temporary.open("wb") as stream:
            while chunk := response.read(1024 * 1024):
                stream.write(chunk)
        temporary.rename(archive)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != digest:
        raise ValueError(f"Checksum mismatch: {archive}; remove only this download and retry")
    # Read only the exact executable, never extract paths or links from a tar.
    with tarfile.open(archive) as upstream:
        binaries = [m for m in upstream.getmembers() if m.isfile()
                    and Path(m.name).name == f"stockfish-linux-{target}-universal"]
        if len(binaries) != 1:
            raise ValueError("Unexpected official archive structure")
        binary = directory / "stockfish"
        with upstream.extractfile(binaries[0]) as stream:
            binary.write_bytes(stream.read())
        header = binary.read_bytes()[:20]
        if header[:4] != b"\x7fELF" or int.from_bytes(header[18:20], "little") != (183 if arch == "aarch64" else 62):
            raise ValueError("Unexpected ELF architecture")
        binary.chmod(0o755)
    manifest = {"version": "19", "architecture": arch, "url": url,
                "archive_sha256": digest,
                "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
                "license": "GPL-3.0-or-later", "source_distribution": "upstream.tar.gz"}
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(binary)
    return binary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arch", choices=ASSETS, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/stockfish")
    args = parser.parse_args()
    download(args.arch, args.output)


if __name__ == "__main__":
    main()
