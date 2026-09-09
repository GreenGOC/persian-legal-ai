from pathlib import Path
import os

from dotenv import load_dotenv
from sentence_transformers import CrossEncoder

from .logging import write_last_query_log


load_dotenv()


def resolve_local_model_path(model_path):
    if not model_path:
        return None

    candidate = Path(model_path).expanduser()

    if not candidate.exists():
        return str(candidate)

    if candidate.is_file() and candidate.name == "config.json":
        return str(candidate.parent)

    if candidate.is_dir():
        if (candidate / "config.json").exists():
            return str(candidate)

        snapshots_dir = candidate / "snapshots"

        if snapshots_dir.is_dir():
            snapshot_dirs = sorted(
                [path for path in snapshots_dir.iterdir() if path.is_dir()],
                key=lambda path: path.name,
            )

            for snapshot_dir in snapshot_dirs:
                if (snapshot_dir / "config.json").exists():
                    return str(snapshot_dir)

    return str(candidate)


class Reranker:
    MIN_SCORE = 0.50
    MAX_SCORE_GAP = 0.2

    def __init__(
        self,
        model_name=None,
        max_length=512,
        device=None,
    ):
        default_model_path = Path(__file__).resolve().parents[3] / "Reranker model"

        model_name = resolve_local_model_path(model_name or os.getenv("RERANKER_MODEL_PATH") or str(default_model_path))

        self.model = CrossEncoder(
            model_name,
            device=device,
            max_length=max_length,
            local_files_only=True,
        )

    def _build_provision_text(self, provision):
        provision_type = {
            "constitutional_principle": "اصل",
            "article": "ماده",
            "note": "تبصره",
            "clause": "بند",
            "subclause": "جزء",
            "item": "جزء",
            "other": "مقرره",
        }.get(
            provision.provision_type,
            "مقرره",
        )

        number = str(provision.number).strip() if provision.number is not None else ""

        title = provision.title.strip() if provision.title else ""

        text = provision.text.strip() if provision.text else ""

        parts = [f"{provision_type} {number}".strip()]

        if title:
            parts.append(title)

        if text:
            parts.append(text)

        return ": ".join(parts)

    def _get_text(self, result):
        provision = result["provision"]
        children = result.get("children", [])

        document = provision.element.document

        parts = []

        if document.title:
            parts.append(document.title.strip())

        # Root provision
        parts.append(self._build_provision_text(provision))

        # Descendant provisions
        for child in children:
            if child.id == provision.id:
                continue

            parts.append(self._build_provision_text(child))

        return "\n".join(parts)

    def rerank(self, query, results, top_k=10):
        if not results:
            return []

        pairs = [
            (
                query,
                self._get_text(result),
            )
            for result in results
        ]

        scores = self.model.predict(
            pairs,
            show_progress_bar=False,
            convert_to_numpy=True,
        )

        reranked_results = [
            {
                "provision": result["provision"],
                "score": float(score),
                "children": result.get(
                    "children",
                    [],
                ),
            }
            for result, score in zip(
                results,
                scores,
            )
        ]

        reranked_results.sort(
            key=lambda result: result["score"],
            reverse=True,
        )

        best_score = reranked_results[0]["score"]

        if best_score < self.MIN_SCORE:
            return []

        min_allowed_score = best_score - self.MAX_SCORE_GAP

        reranked_results = [result for result in reranked_results if (result["score"] >= min_allowed_score and result["score"] >= self.MIN_SCORE)]

        final = reranked_results[:top_k]

        try:
            write_last_query_log(
                "reranker",
                query,
                final,
            )
        except Exception:
            pass

        return final
