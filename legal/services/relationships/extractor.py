import json
from itertools import product
from pathlib import Path
import time

from ..llm.client import LLMClient
from .prompts.annulment import CANCEL_ANNULMENT_SYSTEM_PROMPT
from .prompts.conflict import CONFLICT_SYSTEM_PROMPT
from .prompts.hokumat import HOKUMAT_SYSTEM_PROMPT
from .prompts.modification import MODIFICATION_SYSTEM_PROMPT
from .prompts.reference import REFERENCE_SYSTEM_PROMPT
from .prompts.repeal import REPEAL_SYSTEM_PROMPT
from .prompts.revival import REVIVAL_SYSTEM_PROMPT
from .prompts.takhassos import TAKHASSOS_SYSTEM_PROMPT
from .prompts.takhsis import TAKHSIS_SYSTEM_PROMPT
from .prompts.taqyid import TAQYID_SYSTEM_PROMPT
from .prompts.temporal import TEMPORAL_SYSTEM_PROMPT
from .prompts.implementation import IMPLEMENTATION_SYSTEM_PROMPT
from .prompts.elaboration import ELABORATION_SYSTEM_PROMPT

MAX_TOKENS_PER_GROUP = 8000
TOKENS_PER_WORD = 3
MAX_RELATIONSHIPS = 50

GROUP_CONFIG = {
    "MODIFICATION": {"prompt": MODIFICATION_SYSTEM_PROMPT, "documents": 1},
    "REPEAL": {"prompt": REPEAL_SYSTEM_PROMPT, "documents": 2},
    "CANCEL_ANNULMENT": {"prompt": CANCEL_ANNULMENT_SYSTEM_PROMPT, "documents": 1},
    "TEMPORAL": {"prompt": TEMPORAL_SYSTEM_PROMPT, "documents": 1},
    "CONFLICT": {"prompt": CONFLICT_SYSTEM_PROMPT, "documents": 2},
    "TAKHSIS": {"prompt": TAKHSIS_SYSTEM_PROMPT, "documents": 2},
    "TAQYID": {"prompt": TAQYID_SYSTEM_PROMPT, "documents": 2},
    "TAKHASSOS": {"prompt": TAKHASSOS_SYSTEM_PROMPT, "documents": 1},
    "HOKUMAT": {"prompt": HOKUMAT_SYSTEM_PROMPT, "documents": 2},
    "REFERENCE": {"prompt": REFERENCE_SYSTEM_PROMPT, "documents": 1},
    "ELABORATES": {"prompt": ELABORATION_SYSTEM_PROMPT, "documents": 1},
    "IMPLEMENTS": {"prompt": IMPLEMENTATION_SYSTEM_PROMPT, "documents": 1},
    "REVIVAL": {"prompt": REVIVAL_SYSTEM_PROMPT, "documents": 3},
}


class LegalRelationshipExtractor:
    def __init__(self, llm_client: LLMClient, max_tokens=MAX_TOKENS_PER_GROUP, max_relationships=MAX_RELATIONSHIPS):
        self.llm = llm_client
        self.max_tokens = max_tokens
        self.max_relationships = max_relationships

    def count_tokens(self, text):
        if not text:
            return 0
        return max(1, len(text.split()) * TOKENS_PER_WORD)

    def count_relationships(self, output):
        if not output:
            return 0

        try:
            data = json.loads(output)
        except (json.JSONDecodeError, TypeError):
            start, end = output.find("{"), output.rfind("}")
            if start == -1 or end <= start:
                return 0

            try:
                data = json.loads(output[start:end + 1])
            except json.JSONDecodeError:
                return 0

        if isinstance(data, dict):
            for key in (
                "relationships",
                "relations",
                "modifications",
                "repeals",
                "annulments",
                "cancellations",
                "revivals",
                "temporal",
                "conflicts",
                "takhsis",
                "taqyid",
                "takhassos",
                "hokumat",
                "references",
                "elaborations",
                "implementations",
            ):
                if isinstance(data.get(key), list):
                    return len(data[key])

        return len(data) if isinstance(data, list) else 0

    def build_provision_units(self, document):
        print(f"[BUILD] Document {document.id}: building provision units...", flush=True)
        elements = list(document.elements.select_related("provision", "structural").order_by("order", "id"))
        if not elements:
            print(f"[BUILD] Document {document.id}: no elements.", flush=True)
            return []
        children = {}
        for element in elements:
            if element.parent_id is not None:
                children.setdefault(element.parent_id, []).append(element)

        for items in children.values():
            items.sort(key=lambda x: (x.order, x.id))

        units = []
        current_context = []
        consumed = set()
        for element in elements:
            if element.id in consumed:
                continue
            if element.element_type == "structural":
                structural = element.structural
                text = structural.title.strip()
                if structural.number and structural.number not in text:
                    text = f"{structural.number}, {text}".strip()
                if text:
                    current_context.append(text)

                continue

            provision = element.provision
            text = self._format_provision_text(provision)
            if not text:
                continue

            if provision.provision_type == "article":
                unit_text = "\n".join(current_context + [text])
                current_context = []
                items = []
                self._collect(element, children, items)
                items.sort(key=lambda x: (x.order, x.id))
                parts = [unit_text]
                for item in items:
                    consumed.add(item.id)
                    if item.id == element.id:
                        continue
                    if item.element_type != "provision":
                        continue
                    child_text = self._format_provision_text(item.provision)
                    if child_text:
                        parts.append(child_text)

                units.append({
                    "article_number": provision.number,
                    "article_id": provision.id,
                    "elements": items,
                    "text": "\n".join(parts),
                })

            else:
                unit_text = "\n".join(current_context + [text])
                current_context = []
                consumed.add(element.id)
                units.append({
                    "article_number": None,
                    "article_id": None,
                    "elements": [element],
                    "text": unit_text,
                })

        if current_context:
            units.append({
                "article_number": None,
                "article_id": None,
                "elements": [],
                "text": "\n".join(current_context),
            })
        print(f"[BUILD] Document {document.id}: {len(elements)} elements -> {len(units)} units", flush=True)
        return units

    def _format_provision_text(self, provision):
        text = provision.text.strip()
        if not provision.number:
            return text
        if provision.provision_type == "article":
            prefix = f"ماده {provision.number}"
        elif provision.provision_type == "note":
            prefix = f"تبصره {provision.number}"
        else:
            prefix = provision.number

        return f"{prefix}: {text}" if text else prefix

    def _collect(self, element, children, result):
        result.append(element)

        for child in children.get(element.id, []):
            self._collect(child, children, result)

    def build_groups(self, units):
        groups, current, parts, tokens = [], [], [], 0
        for unit in units:
            unit_tokens = self.count_tokens(unit["text"])
            if unit_tokens > self.max_tokens:
                if current:
                    groups.append(self._make_group(current, parts, tokens))
                    current, parts, tokens = [], [], 0

                groups.append({
                    "index": len(groups),
                    "units": [unit],
                    "provision_count": 1,
                    "token_count": unit_tokens,
                    "text": unit["text"],
                    "oversized": True,
                })
                continue

            if current and tokens + unit_tokens > self.max_tokens:
                groups.append(self._make_group(current, parts, tokens))
                current, parts, tokens = [], [], 0

            current.append(unit)
            parts.append(unit["text"])
            tokens += unit_tokens

        if current:
            groups.append(self._make_group(current, parts, tokens))

        for i, group in enumerate(groups):
            group["index"] = i
            
        print(f"[GROUP] Created {len(groups)} groups, max {self.max_tokens} estimated tokens)", flush=True)

        return groups

    def _make_group(self, units, parts, tokens):
        return {
            "index": None,
            "units": list(units),
            "provision_count": len(units),
            "token_count": tokens,
            "text": "\n\n".join(parts),
            "oversized": False,
        }

    def build_single_document_windows(self, groups):
        return [{
                "groups": [g],
                "text": g["text"],
                "token_count": g["token_count"],
            } for g in groups
        ]

    def build_multi_document_windows(self, document_groups):
        for selected in product(*document_groups):
            text = "\n\n".join(g["text"] for g in selected)
            yield {
                "groups": selected,
                "text": text,
                "token_count": self.count_tokens(text),
            }

    def _extract(self, group_name, text):
        config = GROUP_CONFIG.get(group_name)
        if config is None:
            raise ValueError(f"Unknown relationship group: {group_name}")
        print(f"[LLM] {group_name}: sending request ({self.count_tokens(text)} estimated input tokens)...", flush=True)
        start = time.time()
        output = self.llm.chat(system_prompt=config["prompt"], user_prompt=text, temperature=0)
        elapsed = time.time() - start

        print(f"[LLM] {group_name}: response received in {elapsed:.1f}s", flush=True)

        return output

    def extract_group(self, group_name, text):
        return self._extract(group_name, text)

    def prepare_document(self, document):
        print(f"[PREPARE] Document {document.id}: {document.title}", flush=True)
        units = self.build_provision_units(document)
        return {
            "document_id": document.id,
            "document_title": document.title,
            "units": units,
            "groups": self.build_groups(units),
        }

    def extract_documents(self, group_name, documents, output_dir=None):
        config = GROUP_CONFIG.get(group_name)
        if config is None:
            raise ValueError(f"Unknown relationship group: {group_name}")

        if len(documents) != config["documents"]:
            raise ValueError(f"{group_name} requires {config['documents']} documents.")

        print(f"\n[START] {group_name} | {len(documents)} document(s)", flush=True)
        prepared = [self.prepare_document(d) for d in documents]
        document_groups = [p["groups"] for p in prepared]
        if len(documents) == 1:
            windows = self.build_single_document_windows(document_groups[0])
            total_windows = len(document_groups[0])
        else:
            windows = self.build_multi_document_windows(document_groups)
            total_windows = 1
            for groups in document_groups:
                total_windows *= len(groups)

        print(f"[WINDOWS] {group_name}: {total_windows} window(s)", flush=True)
        results = []
        relationship_count = 0
        for window_index, window in enumerate(windows, 1):
            if relationship_count >= self.max_relationships:
                print(f"[STOP] Reached max relationships({self.max_relationships})", flush=True)
                break

            print(f"[WINDOW] {group_name}: {window_index}/{total_windows} | {window['token_count']} tokens", flush=True)
            try:
                output = self.extract_group(group_name, window["text"])
            except Exception as e:
                print(f"[ERROR] {group_name} window {window_index}: {e}", flush=True)
                if output_dir:
                    self.save_progress(group_name, documents, results, output_dir)

                break


            extracted_count = self.count_relationships(output)
            relationship_count += extracted_count
            print(f"[RESULT] {group_name}: {extracted_count} relationship(s) (total: {relationship_count})", flush=True)
            results.append({
                "documents": [
                    {
                        "document_id": d.id,
                        "document_title": d.title,
                    } for d in documents
                ],

                "groups": [
                    {
                        "index": g["index"],
                        "provision_count": g["provision_count"],
                        "token_count": g["token_count"],
                        "articles": [
                            u["article_number"]
                            for u in g["units"]
                        ],
                    } for g in window["groups"]
                ],

                "input_token_count": window["token_count"],
                "input_text": window["text"],
                "output": output,
                "extracted_relationship_count": extracted_count,
            })


            if output_dir:
                self.save_progress(group_name, documents, results, output_dir)
        print(f"[DONE] {group_name}: {len(results)} window(s), {relationship_count} relationship(s)", flush=True)

        return results

    def extract_document(self, document, group_name):
        return self.extract_documents(group_name, [document])

    def extract_all(self, documents, groups=None):
        groups = list(GROUP_CONFIG) if groups is None else groups
        results = {}

        for group_name in groups:
            if len(documents) != GROUP_CONFIG[group_name]["documents"]:
                continue
            results[group_name] = self.extract_documents(group_name, documents)

        return results

    def save_json(self, data, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with path.open("w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)

    def extract_documents_to_json(self, group_name, documents, output_dir):
        print(f"[SAVE] Preparing output for {group_name}...", flush=True)
        results = self.extract_documents(group_name, documents, output_dir)

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        document_ids = "_".join(str(d.id) for d in documents)
        path = output_dir / f"{document_ids}_{group_name.lower()}.json"

        self.save_json({
            "group_name": group_name,
            "documents": [
                {
                    "document_id": d.id,
                    "document_title": d.title,
                }
                for d in documents
            ],
            "results": results,
        }, path)

        return path
    
    
    def save_progress(self, group_name, documents, results, output_dir):
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        document_ids = "_".join(str(d.id) for d in documents)
        path = output_dir / f"{document_ids}_{group_name.lower()}_progress.json"

        self.save_json({
            "group_name": group_name,
            "documents": [
                {
                    "document_id": d.id,
                    "document_title": d.title,
                }
                for d in documents
            ],
            "results": results,
            "status": "in_progress",
        }, path)

        print(f"[SAVE] Progress saved: {path}", flush=True)

        return path