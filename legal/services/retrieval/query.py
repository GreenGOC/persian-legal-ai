from dataclasses import dataclass

from hazm import Normalizer


@dataclass(frozen=True)
class QueryResult:
    original: str
    normalized: str


class QueryProcessor:
    def __init__(self):
        self.normalizer = Normalizer()

    def process(self, query: str) -> QueryResult:
        if not isinstance(query, str):
            raise TypeError("query must be a string")
        query = query.strip()
        if not query:
            raise ValueError("query cannot be empty")
        normalized = self.normalizer.normalize(query)
        return QueryResult(
            original=query,
            normalized=normalized,
        )
