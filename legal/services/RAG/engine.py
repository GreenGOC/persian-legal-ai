from .context import ContextBuilder
from .prompt import PromptBuilder
from ..llm.client import LLMClient
from ..retrieval.engine import RetrievalEngine
from django.conf import settings


class RAGEngine:
    def __init__(self, max_results=8):
        print("RAGEngine: initializing engine...")
        self.context_builder = ContextBuilder(max_results=max_results)
        self.prompt_builder = PromptBuilder()

        self.llm_client = LLMClient(
            api_key=settings.ROUTER_API_KEY,
            base_url=settings.ROUTER_BASE_URL,
            model=settings.ROUTER_MODEL,
        )
        self.max_results = max_results
        self.retrieval_engine = RetrievalEngine(device="cpu")
        self.retrieval_engine.connect()
        print("RAGEngine: initialization complete.")

    def generate(self, question):
        print("RAGEngine: generate() called with question:", question)
        results = self.retrieval_engine.search(question, rerank_k=self.max_results)
        print("RAGEngine: retrieval returned", len(results) if isinstance(results, list) else type(results).__name__, "items")
        context = self.context_builder.build(results)
        print("RAGEngine: built context length:", len(context) if isinstance(context, str) else type(context).__name__)
        if not context:
            print("RAGEngine: no legal context found for this question.")
            return "برای این پرسش، مستند قانونیِ کافی در سامانه پیدا نشد."
        system_prompt, user_prompt = self.prompt_builder.build(question, context)
        print("RAGEngine: calling LLM with prompt length:", len(system_prompt) + len(user_prompt))
        answer = self.llm_client.chat(system_prompt=system_prompt, user_prompt=user_prompt)
        print("RAGEngine: LLM response received.")
        return answer
