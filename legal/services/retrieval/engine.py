from .bm25 import BM25Retriever
from .dense import DenseRetriever, DenseIndexer, EmbeddingModel
from .hybrid import HybridRetriever
from .query import QueryProcessor
from .reranker import Reranker

class RetrievalEngine:
    def __init__(self, device="cpu"):
        print("RetrievalEngine: initializing retrievers...")
        self.query_processor = QueryProcessor()
        self.embedding_model = EmbeddingModel(device=device)
        self.bm25_retriever = BM25Retriever()
        self.dense_retriever = DenseRetriever(self.embedding_model)
        self.dense_indexer = DenseIndexer(self.embedding_model)
        self.hybrid_retriever = HybridRetriever(bm25_retriever=self.bm25_retriever, dense_retriever=self.dense_retriever)
        self.reranker = Reranker(device=device)
        self.initialized = False
        print("RetrievalEngine: initialization finished.")

    def connect(self):
        print("RetrievalEngine: connecting dense retriever...")
        self.dense_retriever.connect()
        self.initialized = True
        print("RetrievalEngine: connected successfully.")

    def build_indexes(self):
        print("RetrievalEngine: building indexes...")
        self.dense_indexer.connect()
        result = self.dense_indexer.index_all()
        print("RetrievalEngine: index build finished.")
        return result

    def search(self, query, top_k=50, retrieval_k=100, rerank_k=25):
        print("RetrievalEngine: search() called with query:", query)
        if not self.initialized:
            print("RetrievalEngine: not initialized, raising error.")
            raise RuntimeError("RetrievalEngine is not connected!")
        
        processed_query = self.query_processor.process(query)
        print("RetrievalEngine: processed query:", processed_query.normalized)
        candidates = self.hybrid_retriever.search(processed_query.normalized, top_k=top_k, retrieval_k=retrieval_k)
        print("RetrievalEngine: hybrid candidates count:", len(candidates) if isinstance(candidates, list) else type(candidates).__name__)
        reranked = self.reranker.rerank(processed_query.normalized, candidates, top_k=rerank_k)
        print("RetrievalEngine: rerank finished. Final count:", len(reranked) if isinstance(reranked, list) else type(reranked).__name__)
        return reranked
