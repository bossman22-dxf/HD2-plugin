"""
Weapon icon post-processing helpers.

Some support weapon icons use small top-right identifiers that are easier to
maintain as reusable overlays than as one-off hand edits:

- backpack identifier, using HD2-WAS/HD2-SPE style
- expendable identifier, using HD2-SLO/HD2-EAT style

This module patches already-generated PNGs in-place. It extracts only the
identifier pixels from a reference icon by comparing that reference against the
blue blank background, then pastes those pixels into the same position on each
configured target icon.
"""

from __future__ import annotations

from pathlib import Path

try:
    from PIL import Image, ImageChops
except ImportError:  # pragma: no cover - handled at runtime
    Image = None
    ImageChops = None

from .config import ICONS_DIR


# Marker crop boxes are inclusive-left/top, exclusive-right/bottom.
# These were measured from the current HD2-* icon style at 144x144.
IDENTIFIER_SOURCES = {
    "backpack": {
        "reference": "HD2-WAS",
        "blank": "Blank/HD2-Blank-Blue",
        "box": (108, 19, 123, 41),
    },
    "expendable": {
        "reference": "HD2-EAT",
        "blank": "Blank/HD2-Blank-Blue",
        "box": (97, 18, 126, 49),
    },
}


# Manual overlay map. Add entries here when a generated weapon icon needs one of
# the identifiers above. The reference icons themselves already include these
# markers in your local styled PNG source, so this map starts empty.
#
# Examples:
# WEAPON_IDENTIFIER_MAPPINGS = {
#     "HD2-MY-BACKPACK-WEAPON": "backpack",
#     "HD2-MY-EXPENDABLE-WEAPON": "expendable",
# }
WEAPON_IDENTIFIER_MAPPINGS: dict[str, str] = {}


def _png_path(icon_dir: Path, stem: str) -> Path:
    return icon_dir / f"{stem}.png"


def _load_overlay(icon_dir: Path, identifier: str) -> tuple[Image.Image, tuple[int, int, int, int]]:
    """Extract identifier overlay and alpha mask from its reference icon."""
    if Image is None or ImageChops is None:
        raise RuntimeError("Pillow is required for weapon identifier overlays")

    source = IDENTIFIER_SOURCES[identifier]
    box = source["box"]
    reference_path = _png_path(icon_dir, source["reference"])
    blank_path = _png_path(icon_dir, source["blank"])

    if not reference_path.exists():
        raise FileNotFoundError(f"Missing identifier reference icon: {reference_path}")
    if not blank_path.exists():
        raise FileNotFoundError(f"Missing identifier blank icon: {blank_path}")

    reference_crop = Image.open(reference_path).convert("RGBA").crop(box)
    blank_crop = Image.open(blank_path).convert("RGBA").crop(box)

    # Use the difference from the blank as the paste mask. This keeps the marker
    # shape while leaving the target icon/background untouched elsewhere.
    diff = ImageChops.difference(reference_crop, blank_crop).convert("L")
    mask = diff.point(lambda value: 255 if value else 0)
    overlay = Image.new("RGBA", reference_crop.size, (0, 0, 0, 0))
    overlay.paste(reference_crop, (0, 0), mask)
    return overlay, box


def apply_weapon_identifier_overlays(
    icon_dir: Path = ICONS_DIR,
    mappings: dict[str, str] | None = None,
    dry_run: bool = False,
    verbose: bool = False,
) -> tuple[int, int]:
    """
    Apply configured top-right weapon identifiers to existing PNG icons.

    Args:
        icon_dir: Directory containing generated PNG icons.
        mappings: Optional target->identifier mapping. Defaults to
            WEAPON_IDENTIFIER_MAPPINGS.
        dry_run: If True, report actions without modifying files.
        verbose: Print each applied overlay.

    Returns:
        Tuple of (updated_count, error_count).
    """
    mappings = mappings if mappings is not None else WEAPON_IDENTIFIER_MAPPINGS
    if not mappings:
        return 0, 0

    if Image is None or ImageChops is None:
        print("Pillow not found; cannot apply weapon identifier overlays.")
        return 0, len(mappings)

    overlay_cache: dict[str, tuple[Image.Image, tuple[int, int, int, int]]] = {}
    updated = 0
    errors = 0

    for target, identifier in mappings.items():
        if identifier not in IDENTIFIER_SOURCES:
            print(f"  ERROR: {target}: unknown weapon identifier '{identifier}'")
            errors += 1
            continue

        target_path = _png_path(icon_dir, target)
        if not target_path.exists():
            print(f"  ERROR: {target}: target icon not found: {target_path}")
            errors += 1
            continue

        if dry_run:
            if verbose:
                print(f"  {target}.png  <-  {identifier} weapon identifier")
            updated += 1
            continue

        try:
            if identifier not in overlay_cache:
                overlay_cache[identifier] = _load_overlay(icon_dir, identifier)

            overlay, box = overlay_cache[identifier]
            icon = Image.open(target_path).convert("RGBA")
            icon.alpha_composite(overlay, dest=(box[0], box[1]))
            icon.convert("RGB").save(target_path, "PNG")
            updated += 1
            if verbose:
                print(f"  {target}.png  <-  {identifier} weapon identifier")
        except Exception as exc:
            print(f"  ERROR: {target}: failed to apply {identifier} identifier: {exc}")
            errors += 1

    return updated, errors
