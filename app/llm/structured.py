from __future__ import annotations

import json
import re
from typing import Any, Optional

try:
    from json_repair import repair_json
except ImportError:
    repair_json = None


def extract_json(text: str) -> Optional[Any]:
    text = text.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        try:
            return json.loads(fence.group(1).strip())
        except json.JSONDecodeError:
            if repair_json:
                try:
                    return json.loads(repair_json(fence.group(1)))
                except Exception:
                    pass
    if repair_json:
        try:
            return json.loads(repair_json(text))
        except Exception:
            pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        chunk = text[start : end + 1]
        try:
            return json.loads(chunk)
        except json.JSONDecodeError:
            if repair_json:
                try:
                    return json.loads(repair_json(chunk))
                except Exception:
                    pass
    return None
