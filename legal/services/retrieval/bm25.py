import math
from collections import Counter
from heapq import nlargest

from legal.models import ElementType, LegalElement, LegalProvision, StructuralElement

from .logging import write_last_query_log

class BM25:
    def __init__(self, document_count, average_document_length, document_frequencies, k1=1.5, b=0.75):
        self.document_count = document_count
        self.average_document_length = average_document_length
        self.document_frequencies = document_frequencies
        self.k1 = k1
        self.b = b

    def _idf(self, term):
        document_frequency = self.document_frequencies.get(term, 0)
        if document_frequency == 0:
            return 0.0

        return math.log(1 + (self.document_count - document_frequency + 0.5) / (document_frequency + 0.5))

    def score(self, query, document_length, term_frequencies):
        if self.document_count == 0 or self.average_document_length == 0:
            return 0.0

        score = 0.0
        for term in query:
            frequency = term_frequencies.get(term, 0)
            if frequency == 0:
                continue

            idf = self._idf(term)
            numerator = frequency * (self.k1 + 1)
            denominator = frequency + self.k1 * (1 - self.b + self.b * document_length / self.average_document_length)
            score += idf * numerator / denominator
        return score


class BM25Retriever:
    PROVISION_TYPE_LABELS = {
        "constitutional_principle": "اصل",
        "article": "ماده",
        "note": "تبصره",
        "clause": "بند",
        "subclause": "جزء",
        "item": "جزء",
        "other": "مقرره",
    }

    STRUCTURAL_TYPE_LABELS = {
        "book": "کتاب",
        "part": "بخش",
        "chapter": "فصل",
        "section": "مبحث",
        "subsection": "گفتار",
        "introduction": "مقدمه",
        "other": "بخش",
    }

    def __init__(self):
        self.bm25 = None

    def _get_queryset(self):
        return LegalProvision.objects.select_related("element__document").order_by("id")

    def _to_persian_digits(self, value):
        if value is None:
            return ""

        return str(value).translate(
            str.maketrans(
                "0123456789٠١٢٣٤٥٦٧٨٩",
                "۰۱۲۳۴۵۶۷۸۹۰۱۲۳۴۵۶۷۸۹",
            )
        )

    def _get_provision_type_label(self, provision):
        return self.PROVISION_TYPE_LABELS.get(provision.provision_type, "مقرره")

    def _get_structural_type_label(self, structural):
        return self.STRUCTURAL_TYPE_LABELS.get(structural.structural_type, "بخش")

    def _get_root_provision(self, provision, parent_by_element_id, element_type_by_id, provision_by_element_id, root_cache):
        element_id = provision.element_id
        if element_id in root_cache:
            return root_cache[element_id]

        path = []
        current_id = element_id
        while current_id is not None:
            if current_id in root_cache:
                root_id = root_cache[current_id]
                break

            path.append(current_id)
            parent_id = parent_by_element_id.get(current_id)
            if parent_id is None:
                root_id = current_id
                break

            parent_type = element_type_by_id.get(parent_id)
            if parent_type == ElementType.STRUCTURAL:
                root_id = current_id
                break

            current_id = parent_id

        for path_element_id in path:
            root_cache[path_element_id] = root_id

        return provision_by_element_id.get(root_id)

    def _build_search_documents(self, queryset):
        provisions = list(queryset)
        elements = list(LegalElement.objects.only("id", "parent_id", "element_type").order_by("id"))
        parent_by_element_id = {element.id: element.parent_id for element in elements}
        element_type_by_id = {element.id: element.element_type for element in elements}
        provision_by_element_id = {provision.element_id: provision for provision in provisions}
        groups = {}
        root_cache = {}

        for provision in provisions:
            root_provision = self._get_root_provision(provision, parent_by_element_id, element_type_by_id, provision_by_element_id, root_cache)
            if root_provision is None:
                continue

            root_id = root_provision.id
            if root_id not in groups:
                groups[root_id] = []

            groups[root_id].append(provision)
        return groups, parent_by_element_id

    def _build_provision_text(self, provision):
        provision_type = self._get_provision_type_label(provision)
        number = self._to_persian_digits(provision.number).strip()
        title = provision.title.strip() if provision.title else ""
        text = provision.text.strip() if provision.text else ""
        prefix = f"{provision_type} {number}".strip()
        parts = [prefix]
        if title:
            parts.append(title)

        if text:
            parts.append(text)

        return ": ".join(parts)

    def _build_structural_text(self, provision, parent_by_element_id, structural_by_element_id):
        parts = []
        current_id = provision.element_id
        while current_id is not None:
            parent_id = parent_by_element_id.get(current_id)
            if parent_id is None:
                break

            structural = structural_by_element_id.get(parent_id)
            if structural is not None:
                structural_type = self._get_structural_type_label(structural)
                number = self._to_persian_digits(structural.number).strip()
                title = structural.title.strip() if structural.title else ""
                if number and title:
                    parts.append(f"{structural_type} {number}: {title}")
                elif number:
                    parts.append(f"{structural_type} {number}")
                elif title:
                    parts.append(f"{structural_type}: {title}")

            current_id = parent_id
        parts.reverse()
        return " ".join(parts)

    def _build_root_text(self, root_provision, parent_by_element_id, structural_by_element_id):
        provision_type = self._get_provision_type_label(root_provision)
        number = self._to_persian_digits(root_provision.number).strip()
        title = root_provision.title.strip() if root_provision.title else ""
        text = root_provision.text.strip() if root_provision.text else ""
        prefix = f"{provision_type} {number}".strip()
        parts = [prefix]
        if title:
            parts.append(title)

        structural_text = self._build_structural_text(root_provision, parent_by_element_id, structural_by_element_id)
        if structural_text:
            parts.append(structural_text)

        document = root_provision.element.document
        if document.title:
            parts.append(document.title.strip())

        if text:
            parts.append(text)

        return ": ".join(parts)

    def _build_document_text(self, provisions, parent_by_element_id, structural_by_element_id):
        if not provisions:
            return ""

        root_provision = provisions[0]
        parts = [self._build_root_text(root_provision, parent_by_element_id, structural_by_element_id)]
        parts.extend(self._build_provision_text(provision) for provision in provisions[1:])
        return "\n".join(parts)

    def _build_statistics(self, search_documents, query_tokens, parent_by_element_id, structural_by_element_id):
        document_count = 0
        total_document_length = 0
        document_frequencies = Counter()
        query_terms = set(query_tokens)
        for provisions in search_documents.values():
            text = self._build_document_text(provisions, parent_by_element_id, structural_by_element_id)
            tokens = text.split()
            if not tokens:
                continue
            document_count += 1
            total_document_length += len(tokens)
            terms_in_document = set(tokens)
            for term in query_terms:
                if term in terms_in_document:
                    document_frequencies[term] += 1

        average_document_length = total_document_length / document_count if document_count else 0
        return document_count, average_document_length, document_frequencies

    def search(self, query, top_k=30):
        queryset = self._get_queryset()
        query_tokens = query.split()
        if not query_tokens:
            return []

        search_documents, parent_by_element_id = self._build_search_documents(queryset)
        structural_elements = list(StructuralElement.objects.only("element_id", "structural_type", "number", "title"))
        structural_by_element_id = {structural.element_id: structural for structural in structural_elements}
        document_count, average_document_length, document_frequencies = self._build_statistics(search_documents, query_tokens, parent_by_element_id, structural_by_element_id)

        self.bm25 = BM25(document_count=document_count, average_document_length=average_document_length, document_frequencies=document_frequencies,)
        top_results = []

        for root_id, provisions in search_documents.items():
            text = self._build_document_text(provisions, parent_by_element_id, structural_by_element_id)
            tokens = text.split()
            if not tokens:
                continue

            term_frequencies = Counter(tokens)
            score = self.bm25.score(query=query_tokens, document_length=len(tokens), term_frequencies=term_frequencies)
            if score <= 0:
                continue
            
            root_provision = provisions[0]
            top_results.append((score, root_provision, provisions))
            if len(top_results) > top_k:
                top_results = nlargest(top_k, top_results, key=lambda item: item[0])
                
        top_results.sort(key=lambda item: item[0], reverse=True)
        results = [{
                "provision": root_provision,
                "score": score,
                "children": provisions,
            } for score, root_provision, provisions in top_results]
        
        try:
            write_last_query_log("bm25", query, results)
        except Exception:
            pass

        return results
