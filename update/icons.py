"""
Icon generation: Convert SVG stratagem icons to PNG with corner borders.
"""

from __future__ import annotations

import io
import re
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PIL import Image as PILImage

try:
    import cairosvg
except ImportError:
    cairosvg = None

try:
    from PIL import Image, ImageDraw
except ImportError:
    Image = None
    ImageDraw = None

from .config import (
    COLOR_MAPPINGS,
    DEFAULT_ICON_COLOR,
    DEFAULT_ICON_SCALE,
    DEFAULT_ICON_SIZE,
    ICONS_DIR,
    LOCAL_ICON_EXCLUDED_DIRS,
    LOCAL_ICON_SOURCE_DIR,
    STRATAGEM_MAPPINGS,
)


BLANKS_DIR = ICONS_DIR / "Blank"
BLANK_ICON_FILES = {
    "blue": "HD2-Blank-Blue.png",
    "gold": "HD2-Blank-Gold.png",
    "gold_triangles": "HD2-Blank-Gold+Triangles.png",
    "green": "HD2-Blank-Green.png",
    "red": "HD2-Blank-Red.png",
    "yellow": "HD2-Blank-Yellow.png",
}

# Map known SVG accent colors to the hand-made blank backgrounds. These colors
# come from the wiki/SVG source files, not the more saturated old generator
# colors. The blanks already contain the desired muted background/border style.
ACCENT_COLOR_TO_BLANK = {
    "#49adc9": "blue",
    "#c9b269": "gold",
    "#679552": "green",
    "#de7b6c": "red",
    "#f0c628": "yellow",
}


def check_svg_dependencies():
    """Check if dependencies required for SVG fallback rendering are installed."""
    if cairosvg is None or Image is None or ImageDraw is None:
        print("SVG rendering dependencies not found. Install them with:")
        print("  pip install cairosvg pillow")
        return False
    return True


def check_png_dependencies():
    """Check if dependencies for PNG resizing are installed."""
    if Image is None:
        print("Pillow not found; local PNGs will be copied without resizing.")
        print("Install it with: pip install pillow")
        return False
    return True


def normalize_hex_color(color: str) -> str:
    """Normalize a hex color to lowercase 6-character format."""
    color = color.strip().lower()
    if color.startswith('#'):
        hex_part = color[1:]
        if len(hex_part) == 3:
            hex_part = ''.join(c * 2 for c in hex_part)
        return f"#{hex_part}"
    return color


def apply_color_mapping(color: str) -> tuple[str, bool]:
    """
    Apply color mapping to convert SVG colors to PNG colors.
    
    Returns:
        Tuple of (mapped_color, was_mapped)
    """
    normalized = normalize_hex_color(color)
    if normalized in COLOR_MAPPINGS:
        return normalize_hex_color(COLOR_MAPPINGS[normalized]), True
    return normalized, False


def replace_colors_in_svg(svg_content: str, color_map: dict) -> str:
    """Replace colors in SVG content based on a color mapping."""
    result = svg_content
    
    for old_color, new_color in color_map.items():
        old_normalized = normalize_hex_color(old_color)
        new_normalized = normalize_hex_color(new_color)
        
        if old_normalized == new_normalized:
            continue
        
        old_hex = old_normalized[1:]
        new_hex = new_normalized[1:]
        
        result = result.replace(f"#{old_hex}", f"#{new_hex}")
        result = result.replace(f"#{old_hex.upper()}", f"#{new_hex}")
        result = re.sub(
            rf'#({old_hex})',
            f'#{new_hex}',
            result,
            flags=re.IGNORECASE
        )
    
    return result


# Colors to ignore when extracting accent color
IGNORE_COLORS = {
    "#fff", "#ffffff", "#FFF", "#FFFFFF",
    "white", "WHITE", "White",
    "#fefefe", "#FEFEFE",
}


def is_white_color(color: str) -> bool:
    """Check if a color is white or near-white."""
    normalized = normalize_hex_color(color)
    if normalized in IGNORE_COLORS or color in IGNORE_COLORS:
        return True
    
    if normalized.startswith('#') and len(normalized) == 7:
        try:
            r = int(normalized[1:3], 16)
            g = int(normalized[3:5], 16)
            b = int(normalized[5:7], 16)
            if r > 240 and g > 240 and b > 240:
                return True
        except ValueError:
            pass
    
    return False


def _is_hex_color(color: str) -> bool:
    """Check if a string is a valid hex color (#rgb or #rrggbb)."""
    color = color.strip()
    if not color.startswith('#'):
        return False
    hex_part = color[1:]
    if len(hex_part) not in (3, 6):
        return False
    return all(c in '0123456789abcdefABCDEF' for c in hex_part)


def extract_accent_color(svg_content: str) -> tuple[str, bool]:
    """Extract the accent color from an SVG file.
    
    Returns:
        Tuple of (color, used_default_fallback). used_default_fallback is True
        when no valid hex fill was found (e.g. only fill=\"none\") and we fell
        back to DEFAULT_ICON_COLOR.
    """
    colors = []
    
    fill_attr_pattern = re.compile(r'fill\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)
    colors.extend(fill_attr_pattern.findall(svg_content))
    
    style_fill_pattern = re.compile(r'style\s*=\s*["\'][^"\']*fill\s*:\s*([^;"\'\s]+)', re.IGNORECASE)
    colors.extend(style_fill_pattern.findall(svg_content))
    
    for color in colors:
        color = color.strip()
        if not _is_hex_color(color):
            continue
        if not is_white_color(color):
            return normalize_hex_color(color), False
    
    return DEFAULT_ICON_COLOR, True


def has_corner_borders(svg_content: str) -> bool:
    """Detect if an SVG has built-in corner border triangles."""
    d_pattern = re.compile(r'd\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)
    sep = r'[\s,]*'
    
    for d_match in d_pattern.finditer(svg_content):
        d_content = d_match.group(1)
        
        starts_at_corner = bool(re.match(
            rf'M{sep}[0-9]{{1,2}}{sep}(1[12][0-9]|[0-9]{{1,2}}){sep}[Vv]',
            d_content, re.IGNORECASE
        ))
        
        if not starts_at_corner:
            continue
        
        z_count = len(re.findall(r'[Zz]', d_content))
        if z_count != 4:
            continue
        
        m_count = len(re.findall(r'[Mm]', d_content))
        if m_count < 3 or m_count > 5:
            continue
        
        if len(d_content) > 200:
            continue
        
        triangle_pattern = rf'[Vv]{sep}-?\d+{sep}[Ll]{sep}-?\d+{sep}-?\d+{sep}[Hh]{sep}-?\d+{sep}[Zz]'
        triangle_count = len(re.findall(triangle_pattern, d_content, re.IGNORECASE))
        if triangle_count >= 2:
            return True
    
    return False


def remove_corner_borders(svg_content: str) -> str:
    """Remove built-in corner border paths from an SVG."""
    path_pattern = re.compile(
        r'<path\s+[^>]*?d\s*=\s*["\']([^"\']+)["\'][^>]*/?\s*>',
        re.IGNORECASE | re.DOTALL
    )
    
    sep = r'[\s,]*'
    
    def is_corner_border_path(d_attr: str) -> bool:
        d = d_attr
        
        starts_at_corner = bool(re.match(
            rf'M{sep}[0-9]{{1,2}}{sep}(1[12][0-9]|[0-9]{{1,2}}){sep}[Vv]',
            d, re.IGNORECASE
        ))
        
        if not starts_at_corner:
            return False
        
        z_count = len(re.findall(r'[Zz]', d))
        if z_count != 4:
            return False
        
        m_count = len(re.findall(r'[Mm]', d))
        if m_count < 3 or m_count > 5:
            return False
        
        if len(d) > 200:
            return False
        
        triangle_pattern = rf'[Vv]{sep}-?\d+{sep}[Ll]{sep}-?\d+{sep}-?\d+{sep}[Hh]{sep}-?\d+{sep}[Zz]'
        triangle_count = len(re.findall(triangle_pattern, d, re.IGNORECASE))
        if triangle_count < 2:
            return False
        
        return True
    
    def replace_corner_path(match):
        d_attr = match.group(1)
        if is_corner_border_path(d_attr):
            return ''
        return match.group(0)
    
    result = path_pattern.sub(replace_corner_path, svg_content)
    result = re.sub(r'\n\s*\n', '\n', result)
    
    return result


def choose_blank_key(accent_color: str, had_corners: bool) -> str:
    """Choose the local blank background for an SVG accent color."""
    blank_key = ACCENT_COLOR_TO_BLANK.get(normalize_hex_color(accent_color), "gold")
    if blank_key == "gold" and had_corners:
        return "gold_triangles"
    return blank_key


def get_blank_icon_path(accent_color: str, had_corners: bool) -> Path:
    """Return the blank PNG path matching an SVG's accent/border style."""
    blank_key = choose_blank_key(accent_color, had_corners)
    return BLANKS_DIR / BLANK_ICON_FILES[blank_key]


def load_blank_icon(accent_color: str, had_corners: bool, size: int) -> Image.Image:
    """Load the selected hand-made blank background, resizing if needed."""
    blank_path = get_blank_icon_path(accent_color, had_corners)
    if blank_path.exists():
        blank = Image.open(blank_path).convert("RGBA")
        if blank.size != (size, size):
            blank = blank.resize((size, size), Image.Resampling.LANCZOS)
        return blank

    # Fallback only if the blank assets are unavailable. This should not happen
    # in the normal HD2-* workflow, but keeps the generator robust.
    return Image.new("RGBA", (size, size), (41, 41, 41, 255))


def prepare_svg_foreground(svg_content: str) -> tuple[str, str, bool]:
    """
    Prepare source SVG as a foreground layer for compositing over a blank.

    This recreates the manual workflow: use the SVG as the top image layer, but
    remove/mute embedded background/border styling. Built-in corner-border paths
    are removed from the SVG because the selected blank supplies the background,
    border, and mission-triangle treatment.

    Returns:
        Tuple of (prepared_svg_content, original_accent_color, had_corners)
    """
    original_color, _used_default = extract_accent_color(svg_content)
    had_corners = has_corner_borders(svg_content)
    if had_corners:
        svg_content = remove_corner_borders(svg_content)
    return svg_content, original_color, had_corners


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Convert hex color to RGB tuple."""
    hex_color = hex_color.lstrip('#')
    if len(hex_color) == 3:
        hex_color = ''.join(c * 2 for c in hex_color)
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def draw_corner_borders(image: Image.Image, color: str) -> Image.Image:
    """Draw L-shaped gradient corner borders on the image."""
    rgb_color = hex_to_rgb(color)
    
    w, h = image.size
    
    padding = max(int(w * 0.07), 5)
    line_length = max(int(w * 0.50), 35)
    line_width = max(int(w * 0.014), 2)
    corner_radius = max(int(w * 0.06), 6)
    
    result = image.copy().convert("RGBA")
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    
    # Top-left L-shape
    tl_x = padding
    tl_y = padding
    
    for i in range(line_length):
        alpha = int(255 * (1 - (i / line_length) ** 0.7))
        y = tl_y + corner_radius + i
        if y < h - padding:
            draw.line([(tl_x, y), (tl_x + line_width - 1, y)], fill=(*rgb_color, alpha))
    
    for i in range(line_length):
        alpha = int(255 * (1 - (i / line_length) ** 0.7))
        x = tl_x + corner_radius + i
        if x < w - padding:
            draw.line([(x, tl_y), (x, tl_y + line_width - 1)], fill=(*rgb_color, alpha))
    
    draw.arc([tl_x, tl_y, tl_x + corner_radius * 2, tl_y + corner_radius * 2],
             start=180, end=270, fill=(*rgb_color, 255), width=line_width)
    
    # Bottom-right L-shape
    br_x = w - padding - line_width
    br_y = h - padding - line_width
    
    for i in range(line_length):
        alpha = int(255 * (1 - (i / line_length) ** 0.7))
        y = br_y - corner_radius - i
        if y > padding:
            for lw in range(line_width):
                draw.point((br_x + lw, y), fill=(*rgb_color, alpha))
    
    for i in range(line_length):
        alpha = int(255 * (1 - (i / line_length) ** 0.7))
        x = br_x - corner_radius - i
        if x > padding:
            for lw in range(line_width):
                draw.point((x, br_y + lw), fill=(*rgb_color, alpha))
    
    draw.arc([br_x - corner_radius * 2 + line_width - 1, br_y - corner_radius * 2 + line_width - 1,
              br_x + line_width - 1, br_y + line_width - 1],
             start=0, end=90, fill=(*rgb_color, 255), width=line_width)
    
    result = Image.alpha_composite(result, overlay)
    return result


def find_local_style_icons(
    source_dir: Path = LOCAL_ICON_SOURCE_DIR,
    excluded_dirs: set[str] = LOCAL_ICON_EXCLUDED_DIRS,
) -> dict[str, Path]:
    """
    Find local styled PNG icons keyed by filename stem.

    Factions, folder icons, and key icons are intentionally excluded because
    they are organization/navigation assets, not stratagem styling references.
    """
    icons: dict[str, Path] = {}
    if not source_dir.exists():
        return icons

    for png_path in source_dir.rglob("*.png"):
        rel_parts = png_path.relative_to(source_dir).parts
        if any(part in excluded_dirs for part in rel_parts):
            continue
        icons[png_path.stem] = png_path

    return icons


def copy_local_style_icon(source_path: Path, output_path: Path, size: int = DEFAULT_ICON_SIZE) -> None:
    """Copy a local styled PNG icon, resizing only if needed."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if Image is None:
        shutil.copy2(source_path, output_path)
        return

    image = Image.open(source_path)
    if image.size != (size, size):
        image = image.convert("RGBA").resize((size, size), Image.Resampling.LANCZOS)
        image.convert("RGB").save(output_path, "PNG")
        return

    shutil.copy2(source_path, output_path)


def svg_to_png_with_borders(
    svg_path: Path,
    output_path: Path,
    size: int = DEFAULT_ICON_SIZE,
    icon_scale: float = DEFAULT_ICON_SCALE,
) -> tuple[str, str, bool, bool]:
    """
    Convert an SVG to PNG using the HD2-* hand-made blank background style.

    The SVG is rendered as a foreground layer over a blank selected by accent
    color. Embedded SVG corner borders are removed so mission stratagems use the
    Gold+Triangles blank instead of the unwanted original SVG corner styling.

    Returns:
        Tuple of (original_color, blank_key, was_mapped, had_corners)
    """
    svg_content = svg_path.read_text(encoding='utf-8')
    svg_content, original_color, had_corners = prepare_svg_foreground(svg_content)

    _prepared_color, used_default = extract_accent_color(svg_content)
    if used_default:
        print(f"  WARNING: {svg_path.name}: No valid fill color found, using default {DEFAULT_ICON_COLOR}")
    blank_key = choose_blank_key(original_color, had_corners)
    was_mapped = blank_key != "gold" or had_corners
    
    svg_bytes = svg_content.encode('utf-8')
    icon_size = int(size * icon_scale)
    
    png_data = cairosvg.svg2png(
        bytestring=svg_bytes,
        output_width=icon_size,
        output_height=icon_size,
    )
    
    icon = Image.open(io.BytesIO(png_data)).convert("RGBA")
    final_image = load_blank_icon(original_color, had_corners, size)
    
    offset = (size - icon_size) // 2
    final_image.paste(icon, (offset, offset), icon)
    final_image.convert("RGB").save(output_path, "PNG")

    return original_color, blank_key, was_mapped, had_corners


def generate_icons(
    svg_dir: Path,
    output_dir: Path = ICONS_DIR,
    size: int = DEFAULT_ICON_SIZE,
    icon_scale: float = DEFAULT_ICON_SCALE,
    dry_run: bool = False,
    verbose: bool = False,
) -> tuple[int, int]:
    """
    Generate PNG icons from SVG files.

    Iterates config entries rather than SVG files so that multiple entries
    sharing the same svg field (e.g. UploadData, SSDDelivery, ReinforcementPods)
    each get their own correctly-named {key}.png output.

    Args:
        svg_dir: Directory containing SVG category folders
        output_dir: Output directory for PNG files
        size: Icon size in pixels
        icon_scale: Scale factor for the icon within the image
        dry_run: If True, don't actually generate files
        verbose: If True, print detailed output

    Returns:
        Tuple of (converted_count, error_count)
    """
    from .download import find_all_svgs

    local_style_icons = find_local_style_icons()
    if local_style_icons:
        print(f"Found {len(local_style_icons)} local styled PNG icons in {LOCAL_ICON_SOURCE_DIR}")
        check_png_dependencies()

    svg_fallback_available = check_svg_dependencies()

    svgs_by_category = find_all_svgs(svg_dir) if svg_fallback_available else {}

    if not svgs_by_category and not local_style_icons:
        print("No local PNG icons or SVG files found!")
        return 0, 1

    total_svgs = sum(len(svgs) for svgs in svgs_by_category.values())
    if svgs_by_category:
        print(f"Found {total_svgs} SVG files in {len(svgs_by_category)} categories")

    # Build flat lookup: svg_name -> svg_path
    svg_lookup: dict[str, Path] = {
        svg_name: svg_path
        for svgs in svgs_by_category.values()
        for svg_path, svg_name in svgs
    }

    output_dir.mkdir(parents=True, exist_ok=True)

    converted = 0
    errors = 0
    missing: list[str] = []
    failed: list[str] = []

    copied = 0

    for key, data in STRATAGEM_MAPPINGS.items():
        style_icon = data.get('style_icon', key)
        local_icon_path = local_style_icons.get(style_icon) or local_style_icons.get(key)
        output_path = output_dir / f"{key}.png"

        if local_icon_path is not None:
            if dry_run:
                if verbose:
                    print(f"  {key}.png  <-  {local_icon_path} (local styled PNG)")
            else:
                try:
                    copy_local_style_icon(local_icon_path, output_path, size)
                    copied += 1
                    converted += 1
                    if verbose:
                        print(f"  {key}.png  <-  {local_icon_path} (local styled PNG)")
                except Exception as e:
                    print(f'  ERROR: {key} (local icon: "{local_icon_path}"): {e}')
                    errors += 1
                    failed.append(key)
            continue

        svg_name = data.get('svg')
        if not svg_name:
            continue

        if not svg_fallback_available:
            missing.append(f'{key} (local PNG: "{style_icon}", svg fallback unavailable)')
            continue

        if svg_name not in svg_lookup:
            missing.append(f'{key} (svg: "{svg_name}")')
            continue

        svg_path = svg_lookup[svg_name]
        if dry_run:
            svg_content = svg_path.read_text(encoding='utf-8')
            original_color, used_default = extract_accent_color(svg_content)
            if used_default:
                print(f"  WARNING: {svg_name}: No valid fill color found, would use default {DEFAULT_ICON_COLOR}")
            final_color, was_mapped = apply_color_mapping(original_color)
            had_corners = has_corner_borders(svg_content)
            corner_note = " (will remove corners)" if had_corners else ""
            if was_mapped:
                color_info = f"{original_color} -> {final_color}"
            else:
                color_info = final_color
            if verbose:
                print(f"  {key}.png  <-  {svg_name} ({color_info}){corner_note}")
        else:
            try:
                original_color, final_color, was_mapped, had_corners = svg_to_png_with_borders(
                    svg_path, output_path, size, icon_scale
                )
                converted += 1
                if verbose:
                    corner_note = " (removed corners)" if had_corners else ""
                    if was_mapped:
                        color_info = f"{original_color} -> {final_color}"
                    else:
                        color_info = final_color
                    print(f"  {key}.png  <-  {svg_name} ({color_info}){corner_note}")
            except Exception as e:
                print(f'  ERROR: {key} (svg: "{svg_name}"): {e}')
                errors += 1
                failed.append(key)

    if dry_run:
        print(f"\nDry run complete. Would convert {len(STRATAGEM_MAPPINGS)} entries.")
    else:
        try:
            from .weapons import apply_weapon_identifier_overlays

            weapon_updates, weapon_errors = apply_weapon_identifier_overlays(
                output_dir,
                dry_run=dry_run,
                verbose=verbose,
            )
            errors += weapon_errors
            if weapon_updates:
                print(f"  Applied weapon identifier overlays: {weapon_updates}")
        except Exception as e:
            print(f"  ERROR: weapon identifier overlays failed: {e}")
            errors += 1

        print(f"\nConversion complete!")
        print(f"  Converted/copied: {converted}")
        print(f"  Copied local styled PNGs: {copied}")
        if missing:
            print(f"  No SVG found ({len(missing)}): {', '.join(missing)}")
        print(f"  Errors: {errors}")
        if failed:
            print(f"  Failed: {', '.join(failed)}")

    return converted, errors

