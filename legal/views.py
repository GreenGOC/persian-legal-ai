import json
import os
from functools import lru_cache

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET
from django.shortcuts import get_object_or_404
from django.db.models import Q
from .models import LegalDocument, LegalProvision, LegalVersion, LegalRelationship, RelationshipContext

DEMO_MODE = 1

DEMO_DOC_IDS = {
    18346,18591,2542,1015,19189,14583,15461,19770,17458,17409,11861,16737,8168,17368,19772,5919,12896,12980,2884,13899,20103,16460
}

RELATIONSHIP_TYPE_LABELS_FA = {
    "amends": "اصلاحیه",
    "modifies": "تغییر",
    "adds": "الحاق",
    "removes": "حذف",
    "replaces": "جایگزینی",
    "repeals": "نسخ",
    "cancels": "لغو",
    "annuls": "ابطال",
    "suspends": "تعلیق",
    "revives": "احیا",
    "extends": "تمدید",
    "expires": "انقضا",
    "conflicts": "تعارض",
    "takhsis": "تخصیص",
    "taqyid": "تقید",
    "takhassos": "تخصص",
    "hokumat": "حکومت",
    "references": "ارجاع",
    "elaborates": "تبیین",
    "implements": "اجرا",
    "identical": "یکسان",
}


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


@require_GET
def documents_list(request):
    try:
        page = int(request.GET.get('page', '1'))
        if page < 1:
            page = 1
    except Exception:
        page = 1
    try:
        per_page = int(request.GET.get('per_page', '100'))
        per_page = max(1, min(1000, per_page))
    except Exception:
        per_page = 100

    q = request.GET.get('q', '') or request.GET.get('query', '')
    qs = LegalDocument.objects.all()

    if DEMO_MODE:
        qs = qs.filter(id__in=DEMO_DOC_IDS)
    if q:
        import re
        tokens = [t.strip() for t in re.split('[,\s]+', q) if t.strip()]
        for token in tokens:
            qs = qs.filter(Q(title__icontains=token) | Q(subject__icontains=token))

    total_count = qs.count()
    total_pages = (total_count + per_page - 1) // per_page if per_page else 1
    start = (page - 1) * per_page
    end = start + per_page
    docs = qs.order_by('title')[start:end]

    result = []
    for d in docs:
        outgoing_count = LegalRelationship.objects.filter(source__element__document=d).count()
        incoming_count = LegalRelationship.objects.filter(target__element__document=d).count()
        desc = d.subject or d.document_type or ''
        rel_summary = f"روابط: {outgoing_count} ↑ / {incoming_count} ↓"
        summary = (desc + ' • ' + rel_summary).strip(' • ')
        result.append({
            "id": d.id,
            "title": d.title,
            "description": summary,
            "outgoing_relationships": outgoing_count,
            "incoming_relationships": incoming_count,
        })

    return JsonResponse({
        "page": page,
        "per_page": per_page,
        "total_count": total_count,
        "total_pages": total_pages,
        "results": result,
    }, safe=False)


@require_GET
def document_provisions(request, doc_id):
    # Return provisions for a given document id
    document = get_object_or_404(LegalDocument, pk=doc_id)
    elements = document.elements.select_related('provision', 'structural').order_by('order', 'id')
    # We'll produce sections containing all provisions in document order,
    # including provisions under miscellaneous and note sections.
    # Sentences are tokenized using hazm when available.
    try:
        from hazm import sent_tokenize as _hz_sent_tokenize
    except Exception:
        import re

        def _hz_sent_tokenize(text):
            if not text:
                return []
            parts = re.split(r'(?<=[\.!؟!?])\s+', text.strip())
            return [p.strip() for p in parts if p.strip()]

    # Collect every provision in document order, regardless of its parent.
    current_struct = ''
    provisions = []
    for el in elements:
        if el.element_type == 'structural' and hasattr(el, 'structural'):
            current_struct = el.structural.title or ''
            continue

        if el.element_type == 'provision' and hasattr(el, 'provision'):
            p = el.provision
            versions = []
            texts = []
            if p.text:
                texts.append(p.text)
            for v in p.versions.all().order_by('created_at'):
                if v.text and v.text != p.text:
                    versions.append({"text": v.text, "version_date": v.version_date, "status": v.status})
                    texts.append(v.text)

            combined = "\n\n".join(texts).strip()
            sentences = _hz_sent_tokenize(combined)

            type_label = "" if p.provision_type == 'other' else {
                'constitutional_principle': 'اصل',
                'article': 'ماده',
                'note': 'تبصره',
                'clause': 'بند',
                'subclause': 'تبصره فرعی',
                'item': 'مورد',
            }.get(p.provision_type, p.provision_type or "")
            display_label = f"{type_label} {p.number or ''}".strip()
            if not display_label or display_label in {"متفرقه", "مقدمه"}:
                display_label = (p.title or "").strip()
            if display_label in {"متفرقه", "مقدمه"}:
                display_label = p.number or ""

            title = (p.title or "").strip()
            if title in {"متفرقه", "مقدمه", "introduction"}:
                title = ""

            prov_entry = {
                "id": p.id,
                "provision_type": p.provision_type,
                "number": p.number,
                "title": title,
                "display_label": display_label,
                "sentences": sentences,
                "versions": versions,
                "children": [],
            }
            provisions.append({"structural": current_struct or '', "provision": prov_entry})

    # Build sections without collapsing any provision into another one.
    sections = []
    for item in provisions:
        struct_title = (item.get('structural') or '').strip()
        if struct_title.lower() in {"متفرقه", "مقدمه", "introduction"}:
            struct_title = ""
        prov = item['provision']

        if sections and sections[-1].get('title') == struct_title:
            sections[-1]['provisions'].append(prov)
        else:
            sections.append({"title": struct_title, "provisions": [prov]})

    return JsonResponse({"document_id": document.id, "title": document.title, "sections": sections})


@require_GET
def relationships(request):
    # Accept either provision_id (pk) or provision_number
    provision_id = request.GET.get('provision_id') or request.GET.get('id')
    provision_number = request.GET.get('provision_number') or request.GET.get('number')

    provision = None
    if provision_id:
        try:
            provision = LegalProvision.objects.select_related('element__document').get(pk=int(provision_id))
        except Exception:
            provision = None

    if provision is None and provision_number:
        try:
            provision = LegalProvision.objects.select_related('element__document').filter(number=provision_number).first()
        except Exception:
            provision = None

    if provision is None:
        return JsonResponse({"error": "provision not found"}, status=404)

    out_rels = []
    for rel in provision.outgoing_relationships.select_related('target__element__document').all():
        contexts = [
            {
                "source_text": c.relationship.source.text,
                "target_text": c.relationship.target.text,
                "old_text": c.old_text,
                "new_text": c.new_text,
            }
            for c in rel.contexts.all()
        ]
        out_rels.append({
            "id": rel.id,
            "relationship_type": rel.relationship_type,
            "relationship_type_fa": RELATIONSHIP_TYPE_LABELS_FA.get(rel.relationship_type, rel.relationship_type),
            "confidence": rel.confidence,
            "target": {
                "id": rel.target.id,
                "number": rel.target.number,
                "title": rel.target.title,
                "document_title": rel.target.element.document.title,
            },
            "contexts": contexts,
        })

    in_rels = []
    for rel in provision.incoming_relationships.select_related('source__element__document').all():
        contexts = [
            {
                "source_text": c.relationship.source.text,
                "target_text": c.relationship.target.text,
                "old_text": c.old_text,
                "new_text": c.new_text,
            }
            for c in rel.contexts.all()
        ]
        in_rels.append({
            "id": rel.id,
            "relationship_type": rel.relationship_type,
            "relationship_type_fa": RELATIONSHIP_TYPE_LABELS_FA.get(rel.relationship_type, rel.relationship_type),
            "confidence": rel.confidence,
            "source": {
                "id": rel.source.id,
                "number": rel.source.number,
                "title": rel.source.title,
                "document_title": rel.source.element.document.title,
            },
            "contexts": contexts,
        })

    return JsonResponse({"provision": {"id": provision.id, "number": provision.number, "title": provision.title}, "outgoing": out_rels, "incoming": in_rels})
