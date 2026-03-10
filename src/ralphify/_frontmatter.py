import re


MAX_OUTPUT_LEN = 5000


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Parse a markdown file with optional YAML-like frontmatter.

    Frontmatter is delimited by --- lines. Only flat key: value pairs
    are supported. Returns (frontmatter_dict, body_text).
    """
    frontmatter: dict = {}
    body = text

    stripped = text.strip()
    if stripped.startswith("---"):
        lines = text.split("\n")
        # Find the opening ---
        start = None
        for i, line in enumerate(lines):
            if line.strip() == "---":
                if start is None:
                    start = i
                else:
                    # Found closing ---
                    fm_lines = lines[start + 1 : i]
                    body = "\n".join(lines[i + 1 :]).strip()
                    for fm_line in fm_lines:
                        fm_line = fm_line.strip()
                        if not fm_line or fm_line.startswith("#"):
                            continue
                        if ":" not in fm_line:
                            continue
                        key, _, value = fm_line.partition(":")
                        key = key.strip()
                        value = value.strip()
                        # Type coercion
                        if key == "timeout":
                            frontmatter[key] = int(value)
                        elif key == "enabled":
                            frontmatter[key] = value.lower() in ("true", "yes", "1")
                        else:
                            frontmatter[key] = value
                    break

    body = re.sub(r"<!--.*?-->", "", body, flags=re.DOTALL).strip()
    return frontmatter, body
