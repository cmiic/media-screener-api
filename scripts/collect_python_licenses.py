import re
import shutil
from importlib.metadata import Distribution, distributions
from pathlib import Path

OUTPUT_DIR = Path("/app/THIRD_PARTY_LICENSES")
LICENSE_FALLBACKS = {
    "flatbuffers": Path("/usr/share/common-licenses/Apache-2.0"),
    "nudenet": Path("/app/LICENSES/AGPL-3.0-or-later.txt"),
}
LICENSE_OVERRIDES = {
    "flatbuffers": "Apache-2.0",
    "nudenet": "AGPL-3.0",
}


def package_directory(distribution: Distribution) -> Path:
    name = distribution.metadata["Name"]
    normalized_name = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return OUTPUT_DIR / f"{normalized_name}-{distribution.version}"


def license_files(distribution: Distribution) -> list[Path]:
    files = []
    for relative_path in distribution.files or ():
        path_text = str(relative_path).lower()
        filename = Path(relative_path).name.lower()
        if ".dist-info/licenses/" in path_text or filename.startswith(("license", "copying", "notice")):
            source = Path(distribution.locate_file(relative_path))
            if source.is_file():
                files.append(source)
    return files


def copy_license_files(distribution: Distribution) -> int:
    destination = package_directory(distribution)
    copied = 0
    for source in license_files(distribution):
        destination.mkdir(parents=True, exist_ok=True)
        target = destination / source.name
        if target.exists():
            target = destination / f"{copied}-{source.name}"
        shutil.copy2(source, target)
        copied += 1

    fallback = LICENSE_FALLBACKS.get(distribution.metadata["Name"].lower())
    if fallback and copied == 0:
        if not fallback.is_file():
            raise RuntimeError(f"License fallback not found: {fallback}")
        destination.mkdir(parents=True, exist_ok=True)
        shutil.copy2(fallback, destination / fallback.name)
        copied = 1

    return copied


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    notices = ["Runtime Python dependencies", "===========================", ""]
    missing_licenses = []

    for distribution in sorted(distributions(), key=lambda item: item.metadata["Name"].lower()):
        name = distribution.metadata["Name"]
        license_name = (
            LICENSE_OVERRIDES.get(name.lower())
            or distribution.metadata.get("License-Expression")
            or distribution.metadata.get("License")
            or "See bundled license file"
        )
        copied = copy_license_files(distribution)
        notices.append(f"{name} {distribution.version}: {license_name}")
        if copied == 0:
            missing_licenses.append(f"{name} {distribution.version}")

    (OUTPUT_DIR / "NOTICE.txt").write_text("\n".join(notices) + "\n", encoding="utf-8")
    if missing_licenses:
        raise RuntimeError(f"Missing dependency license files: {', '.join(missing_licenses)}")


if __name__ == "__main__":
    main()
