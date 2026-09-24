"""Minimal YAML subset reader — standard library only.

This project ships no dependencies, so PyYAML is unavailable. This module reads
the narrow YAML subset that taxonomy.yaml uses:

  * block mappings          key: value
  * nested block mappings   key:  (followed by an indented block)
  * block sequences         - value
  * sequences of mappings   - key: value  (plus deeper indented keys)
  * flow sequences          key: [a, b, c]
  * scalars                 str, int, float, bool, null
  * single/double quotes, and `#` comments outside quotes

It is deliberately NOT a general YAML implementation: no anchors, aliases,
multi-line scalars, multi-document streams, or complex keys. If the taxonomy
grows beyond this subset, replace this module rather than extending it.
"""

_TRUE = {"true", "yes", "on"}
_FALSE = {"false", "no", "off"}
_NULL = {"null", "~", ""}


def _strip_comment(line):
    """Remove a trailing # comment, respecting quoted spans."""
    out = []
    quote = None
    i = 0
    while i < len(line):
        ch = line[i]
        if quote:
            if ch == "\\" and i + 1 < len(line):
                out.append(ch)
                out.append(line[i + 1])
                i += 2
                continue
            if ch == quote:
                quote = None
            out.append(ch)
        else:
            if ch in ('"', "'"):
                quote = ch
                out.append(ch)
            elif ch == "#":
                break
            else:
                out.append(ch)
        i += 1
    return "".join(out).rstrip()


def _unquote(text):
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ('"', "'"):
        body = text[1:-1]
        if text[0] == '"':
            body = body.replace("\\\\", "\x00").replace('\\"', '"')
            body = body.replace("\\n", "\n").replace("\\t", "\t")
            body = body.replace("\x00", "\\")
        return body
    return None


def _scalar(text):
    text = text.strip()
    unq = _unquote(text)
    if unq is not None:
        return unq  # quoted -> always a string, e.g. "6" stays "6"
    if text.startswith("[") and text.endswith("]"):
        inner = text[1:-1].strip()
        if not inner:
            return []
        return [_scalar(part) for part in _split_flow(inner)]
    low = text.lower()
    if low in _TRUE:
        return True
    if low in _FALSE:
        return False
    if low in _NULL:
        return None
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        pass
    return text


def _split_flow(inner):
    """Split a flow-sequence body on commas outside quotes."""
    parts, buf, quote = [], [], None
    for ch in inner:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
        elif ch in ('"', "'"):
            quote = ch
            buf.append(ch)
        elif ch == ",":
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    if buf:
        parts.append("".join(buf))
    return [p.strip() for p in parts if p.strip()]


def _tokenize(text):
    lines = []
    for raw in text.splitlines():
        stripped = _strip_comment(raw)
        if not stripped.strip():
            continue
        indent = len(stripped) - len(stripped.lstrip(" "))
        lines.append((indent, stripped.strip()))
    return lines


def _parse_block(lines, i, indent):
    if i < len(lines) and lines[i][1].startswith("- "):
        return _parse_seq(lines, i, indent)
    if i < len(lines) and lines[i][1] == "-":
        return _parse_seq(lines, i, indent)
    return _parse_map(lines, i, indent)


def _parse_seq(lines, i, indent):
    items = []
    while i < len(lines) and lines[i][0] == indent:
        line = lines[i][1]
        if not (line.startswith("- ") or line == "-"):
            break
        content = line[2:].strip() if line.startswith("- ") else ""
        i += 1
        if not content:
            if i < len(lines) and lines[i][0] > indent:
                sub, i = _parse_block(lines, i, lines[i][0])
                items.append(sub)
            else:
                items.append(None)
            continue
        # "- key: value" starts a mapping whose remaining keys are indented deeper.
        key, sep, rest = _partition_key(content)
        if sep:
            child_indent = indent + 2
            synth = [(child_indent, content)]
            while i < len(lines) and lines[i][0] > indent:
                synth.append((child_indent, lines[i][1]) if lines[i][0] == child_indent else lines[i])
                i += 1
            sub, _ = _parse_block(synth, 0, child_indent)
            items.append(sub)
        else:
            items.append(_scalar(content))
    return items, i


def _partition_key(content):
    """Split 'key: value' on the first colon that is outside quotes.

    Returns (key, found_separator, rest). A bare scalar returns ('', False, '').
    """
    quote = None
    for idx, ch in enumerate(content):
        if quote:
            if ch == quote:
                quote = None
            continue
        if ch in ('"', "'"):
            quote = ch
            continue
        if ch == ":":
            after = content[idx + 1:]
            if after == "" or after.startswith(" "):
                return content[:idx].strip(), True, after.strip()
    return "", False, ""


def _parse_map(lines, i, indent):
    out = {}
    while i < len(lines) and lines[i][0] == indent:
        line = lines[i][1]
        if line.startswith("- ") or line == "-":
            break
        key, sep, rest = _partition_key(line)
        if not sep:
            raise ValueError("cannot parse YAML line: %r" % line)
        key = _unquote(key) or key
        i += 1
        if rest == "":
            if i < len(lines) and lines[i][0] > indent:
                sub, i = _parse_block(lines, i, lines[i][0])
                out[key] = sub
            else:
                out[key] = None
        else:
            out[key] = _scalar(rest)
    return out, i


def loads(text):
    """Parse a YAML string into Python data."""
    lines = _tokenize(text)
    if not lines:
        return {}
    value, _ = _parse_block(lines, 0, lines[0][0])
    return value


def load_path(path):
    """Parse a YAML file at `path`."""
    with open(path, "r", encoding="utf-8") as handle:
        return loads(handle.read())
