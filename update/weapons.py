"""Apply version-controlled SVG identifiers to generated support-weapon icons."""
from __future__ import annotations

import argparse
import io
from pathlib import Path

try:
    import cairosvg
except ImportError:  # pragma: no cover - checked at runtime
    cairosvg = None

try:
    from PIL import Image
except ImportError:  # pragma: no cover - checked at runtime
    Image = None

from .config import ICONS_DIR, SCRIPTS_DIR

IDENTIFIER_DIR = SCRIPTS_DIR / "weapon-identifiers"

# Target icon filename -> reusable master SVG identifier.
# These are deliberately maintained here rather than by editing generated PNGs.
WEAPON_IDENTIFIER_MAPPINGS: dict[str, str] = {
    "HD2-AC": "backpack",
    "HD2-ABR": "backpack",
    "HD2-RR": "backpack",
    "HD2-SPE": "backpack",
    "HD2-WAS": "backpack",
    "HD2-EAT": "expendable",
    "HD2-MLS": "expendable",
}


def _render_identifier(name: str, size: tuple[int, int]) -> Image.Image:
    """Render a transparent master SVG to an RGBA overlay."""
    if cairosvg is None or Image is None:
        raise RuntimeError("CairoSVG and Pillow are required (see update/requirements.txt)")
    svg_path = IDENTIFIER_DIR / f"{name}.svg"
    if not svg_path.is_file():
        raise FileNotFoundError(f"Missing master weapon identifier SVG: {svg_path}")
    png_bytes = cairosvg.svg2png(
        bytestring=svg_path.read_bytes(), output_width=size[0], output_height=size[1]
    )
    return Image.open(io.BytesIO(png_bytes)).convert("RGBA")


def apply_weapon_identifier_overlays(
    icon_dir: Path = ICONS_DIR,
    mappings: dict[str, str] | None = None,
    dry_run: bool = False,
    verbose: bool = False,
) -> tuple[int, int]:
    """Apply the configured SVG identifier to each generated PNG in-place."""
    mappings = mappings if mappings is not None else WEAPON_IDENTIFIER_MAPPINGS
    if not mappings:
        print("No weapon identifier mappings configured.")
        return 0, 0
    if cairosvg is None or Image is None:
        print("ERROR: install CairoSVG and Pillow from update/requirements.txt")
        return 0, len(mappings)

    updated = errors = 0
    cache: dict[str, Image.Image] = {}
    for target, identifier in mappings.items():
        if identifier not in {"backpack", "expendable"}:
            print(f"ERROR: {target}: unknown identifier '{identifier}'")
            errors += 1
            continue
        target_path = icon_dir / f"{target}.png"
        if not target_path.is_file():
            print(f"ERROR: {target}: generated icon not found: {target_path}")
            errors += 1
            continue
        if dry_run:
            print(f"Would apply {identifier} SVG to {target_path.name}")
            updated += 1
            continue
        try:
            with Image.open(target_path) as source:
                icon = source.convert("RGBA")
            if identifier not in cache:
                cache[identifier] = _render_identifier(identifier, icon.size)
            icon.alpha_composite(cache[identifier])
            icon.convert("RGB").save(target_path, "PNG")
            updated += 1
            if verbose:
                print(f"Applied {identifier} SVG to {target_path.name}")
        except Exception as exc:
            print(f"ERROR: {target}: could not apply {identifier} identifier: {exc}")
            errors += 1

    print(f"Weapon identifiers: {updated} applied, {errors} error(s).")
    return updated, errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Report actions without changing PNGs")
    parser.add_argument("-v", "--verbose", action="store_true", help="Print each applied identifier")
    args = parser.parse_args()
    _, errors = apply_weapon_identifier_overlays(dry_run=args.dry_run, verbose=args.verbose)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
