from .logging import write_last_query_log


class HybridRetriever:
    def __init__(
        self,
        bm25_retriever=None,
        dense_retriever=None,
        rrf_k=60,
    ):
        self.bm25_retriever = bm25_retriever
        self.dense_retriever = dense_retriever
        self.rrf_k = rrf_k

    def _rrf_score(self, rank):
        return 1.0 / (self.rrf_k + rank)

    def search(
        self,
        query,
        top_k=30,
        retrieval_k=100,
    ):
        bm25_results = self.bm25_retriever.search(
            query,
            top_k=retrieval_k,
        )

        dense_results = self.dense_retriever.search(
            query,
            top_k=retrieval_k,
        )

        scores = {}
        groups = {}

        for rank, result in enumerate(
            bm25_results,
            start=1,
        ):
            provision = result["provision"]
            provision_id = provision.id

            scores.setdefault(
                provision_id,
                0.0,
            )

            scores[provision_id] += self._rrf_score(rank)

            groups[provision_id] = {
                "provision": provision,
                "children": result.get(
                    "children",
                    [],
                ),
            }

        for rank, result in enumerate(
            dense_results,
            start=1,
        ):
            provision = result["provision"]
            provision_id = provision.id

            scores.setdefault(
                provision_id,
                0.0,
            )

            scores[provision_id] += self._rrf_score(rank)

            if provision_id not in groups:
                groups[provision_id] = {
                    "provision": provision,
                    "children": result.get(
                        "children",
                        [],
                    ),
                }

        ranked_results = sorted(
            scores.items(),
            key=lambda item: item[1],
            reverse=True,
        )

        results = []

        for provision_id, score in ranked_results[:top_k]:
            group = groups[provision_id]

            results.append(
                {
                    "provision": group["provision"],
                    "score": score,
                    "children": group["children"],
                }
            )

        try:
            write_last_query_log(
                "hybrid",
                query,
                results,
            )
        except Exception:
            pass

        return results
