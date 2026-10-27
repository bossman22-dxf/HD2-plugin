"""Apply exact in-game weapon identifiers to generated support-weapon icons.

The tiny transparent PNG masters are pixel-exact crops extracted from the original
styled reference icons supplied by the project maintainer. They are kept outside
the generated icon directory so asset regeneration cannot overwrite them.
"""
from __future__ import annotations

import argparse
from pathlib import Path

try:
    from PIL import Image
except ImportError:  # pragma: no cover - handled at runtime
    Image = None

from .config import ICONS_DIR

IDENTIFIER_DIR = Path(__file__).resolve().parent / "weapon-identifiers"

# Master overlay file and its top-left placement on a 144x144 icon.
IDENTIFIER_SOURCES: dict[str, tuple[str, tuple[int, int]]] = {
    "backpack": ("backpack.png", (108, 19)),
    "expendable": ("expendable.png", (97, 18)),
}

# Icons that do not already include the relevant marker.
WEAPON_IDENTIFIER_MAPPINGS: dict[str, str] = {
    "HD2-AC": "backpack",
    "HD2-ABR": "backpack",
    "HD2-RR": "backpack",
    "HD2-SPE": "backpack",
    "HD2-MLS": "expendable",
}


def _load_overlay(identifier: str) -> tuple[Image.Image, tuple[int, int]]:
    if Image is None:
        raise RuntimeError("Pillow is required for weapon identifier overlays")
    filename, position = IDENTIFIER_SOURCES[identifier]
    master_path = IDENTIFIER_DIR / filename
    if not master_path.is_file():
        raise FileNotFoundError(f"Missing master weapon identifier PNG: {master_path}")
    with Image.open(master_path) as source:
        overlay = source.convert("RGBA")
    return overlay, position


def apply_weapon_identifier_overlays(
    icon_dir: Path = ICONS_DIR,
    mappings: dict[str, str] | None = None,
    dry_run: bool = False,
    verbose: bool = False,
) -> tuple[int, int]:
    """Apply configured pixel-exact PNG overlays to generated icons in-place."""
    mappings = mappings if mappings is not None else WEAPON_IDENTIFIER_MAPPINGS
    if not mappings:
        print("No weapon identifier mappings configured.")
        return 0, 0
    if Image is None:
        print("ERROR: install Pillow from update/requirements.txt")
        return 0, len(mappings)

    overlay_cache: dict[str, tuple[Image.Image, tuple[int, int]]] = {}
    updated = errors = 0
    for target, identifier in mappings.items():
        if identifier not in IDENTIFIER_SOURCES:
            print(f"ERROR: {target}: unknown weapon identifier '{identifier}'")
            errors += 1
            continue
        target_path = icon_dir / f"{target}.png"
        if not target_path.is_file():
            print(f"ERROR: {target}: target icon not found: {target_path}")
            errors += 1
            continue
        if dry_run:
            if verbose:
                print(f"Would apply {identifier} PNG to {target_path.name}")
            updated += 1
            continue
        try:
            if identifier not in overlay_cache:
                overlay_cache[identifier] = _load_overlay(identifier)
            overlay, position = overlay_cache[identifier]
            with Image.open(target_path) as source:
                icon = source.convert("RGBA")
            if icon.size != (144, 144):
                raise ValueError(f"expected a 144x144 icon, got {icon.size}")
            icon.alpha_composite(overlay, dest=position)
            icon.convert("RGB").save(target_path, "PNG")
            updated += 1
            if verbose:
                print(f"Applied {identifier} PNG to {target_path.name}")
        except Exception as exc:
            print(f"ERROR: {target}: failed to apply {identifier} identifier: {exc}")
            errors += 1

    print(f"Weapon identifiers: {updated} applied, {errors} error(s).")
    return updated, errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Report actions without changing PNGs")
    parser.add_argument("-v", "--verbose", action="store_true", help="Print each applied overlay")
    args = parser.parse_args()
    _, errors = apply_weapon_identifier_overlays(dry_run=args.dry_run, verbose=args.verbose)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
