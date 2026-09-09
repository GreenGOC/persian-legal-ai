from pathlib import Path
import json
from typing import List, Dict, Any

def _get_project_root(file_path: Path) -> Path:
    resolved = file_path.resolve()
    for parent in resolved.parents:
        if (parent / "manage.py").exists():
            return parent
        
    try:
        return resolved.parents[3]
    except Exception:
        return resolved


def _provision_to_dict(provision) -> Dict[str, Any]:
    element = getattr(provision, "element", None)
    document = getattr(element, "document", None)
    return {
        "id": getattr(provision, "id", None),
        "number": getattr(provision, "number", None),
        "title": getattr(provision, "title", None),
        "document_title": (getattr(document, "title", None) if document is not None else None),
        "text_snippet": (getattr(provision, "text", "")[:500] if getattr(provision, "text", None) else None),
    }


def write_last_query_log(level: str, query: str, results: List[Dict[str, Any]], base_file: str = None) -> None:
    caller_file = Path(__file__)
    project_root = _get_project_root(caller_file)
    logs_dir = project_root / "logs"
    try:
        logs_dir.mkdir(exist_ok=True)
    except Exception as e:
        print("[WARNING] For this specific reason, we were unable to create the folder: ", e)
        
    out_path = Path(base_file) if base_file else logs_dir / f"last_query_{level}.json"
    serializable = []
    for item in results or []:
        provision = item.get("provision")
        score = item.get("score")
        children = item.get("children", [])
        provision_dict = _provision_to_dict(provision) if provision is not None else {}
        provision_dict.update({"score": score, "children": [_provision_to_dict(child) for child in children if child is not None]})
        serializable.append(provision_dict)

    payload = {
        "level": level,
        "query": query,
        "count": len(serializable),
        "results": serializable,
    }

    try:
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print("[WARNING] For this specific reason, we were unable to write to the file: ", e)
