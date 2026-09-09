import json
from functools import lru_cache

from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt


@lru_cache(maxsize=1)
def get_rag_engine():
    from .services.RAG.engine import RAGEngine

    return RAGEngine()


@csrf_exempt
@require_POST
def chat(request):
    print("Django: /api/chat/ reached with request body:", request.body[:500])
    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        print("Django: invalid JSON body in /api/chat/")
        return JsonResponse({"error": "بدنهٔ درخواست معتبر نیست."}, status=400)

    question = payload.get("question")
    print("Django: parsed question:", question)
    if not isinstance(question, str) or not question.strip():
        print("Django: question missing or empty in /api/chat/")
        return JsonResponse({"error": "لطفاً سوال خود را وارد کنید."}, status=400)
    if len(question) > 4000:
        print("Django: question too long in /api/chat/", len(question))
        return JsonResponse(
            {"error": "سوال نمی‌تواند بیشتر از ۴۰۰۰ کاراکتر باشد."}, status=400
        )
    try:
        print("Django: calling RAG engine for question:", question)
        result = get_rag_engine().generate(question)
        print("Django: RAG engine returned type:", type(result).__name__)
    except Exception as exc:
        print("Django: error while generating answer in /api/chat/", exc)
        return JsonResponse(
            {"error": "پاسخ‌گویی در حال حاضر در دسترس نیست. لطفاً دوباره تلاش کنید."},
            status=503,
        )
    if isinstance(result, dict):
        print("Django: returning dict response from /api/chat/")
        return JsonResponse(result)
    if isinstance(result, str):
        print("Django: returning string response from /api/chat/")
        return JsonResponse({"answer": result})
    print("Django: returning fallback string response from /api/chat/")
    return JsonResponse({"answer": str(result)})
