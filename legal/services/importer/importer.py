import json
import re
import hashlib

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from django.db import transaction
from ..utility.normalizer import *

from ...models import (
    LegalVersion,
    DocumentType,
    DocumentStatus,
    ElementType,
    StructuralType,
    ProvisionType,
    LegalEntity,
    SourceDocument,
    LegalDocument,
    DocumentSource,
    LegalElement,
    StructuralElement,
    LegalProvision,
    HierarchyLevel,
)


def read_file(path: str | Path) -> Dict[str, Any]:
    path = Path(path)
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Invalid document root in {path}")
    return data


def check_non_iranian(value: str) -> bool:
    return normalizer.normalize("قانون خارجی") in normalize_text(value)


def get_issuing_authority(value: str) -> str:
    return normalize_text(value).split("-")[0].strip()


def extract_document_metadata(data: Dict[str, Any]) -> Dict[str, Any]:
    category = data.get("category", "")
    metadata = {
        "id": normalize_text(data.get("id", "")),
        "title": normalize_text(data.get("title", "")),
        "url": normalize_text(data.get("url", "")),
        "approval_date": normalize_text(data.get("approval_date", "")),
        "category": normalize_text(category),
        "publication_date": normalize_text(data.get("publication_date")),
        "is_iranian": False if check_non_iranian(category) else True,
        "issuing_authority": get_issuing_authority(category),
    }
    return metadata


DOCUMENT_TYPE_RULES = [
    (
        DocumentType.EXECUTIVE_RESOLUTION,
        [
            "تصویب نامه اجرایی",
            "تصویب‌نامه اجرایی",
        ],
    ),
    (
        DocumentType.RESOLUTION,
        [
            "تصویب نامه",
            "تصویب‌نامه",
            "مصوبه",
            "مصوبات",
        ],
    ),
    (
        DocumentType.BYLAW,
        [
            "اساسنامه",
        ],
    ),
    (
        DocumentType.REGULATION,
        [
            "آیین نامه",
            "آیین‌نامه",
        ],
    ),
    (
        DocumentType.CIRCULAR,
        [
            "بخشنامه",
        ],
    ),
    (
        DocumentType.DECREE,
        [
            "دستورالعمل",
            "ابلاغیه",
            "دستور ابلاغ",
        ],
    ),
    (
        DocumentType.LAW,
        [
            "قانون",
        ],
    ),
]


def determine_hierarchy(metadata: Dict[str, Any], document_type: str) -> str:
    title = normalize_text(metadata["title"])
    authority = normalize_text(metadata["issuing_authority"])

    if title.startswith("قانون اساسی"):
        return HierarchyLevel.CONSTITUTION
    if "مجلس شورای اسلامی" in authority or "مجلس" in authority:
        return HierarchyLevel.ORDINARY_LAW
    if "مجمع تشخیص مصلحت نظام" in authority or "مجمع تشخیص" in authority:
        return HierarchyLevel.ORDINARY_LAW
    if "هیئت وزیران" in authority or "وزیر" in authority or "وزارت" in authority or "سازمان" in authority or "معاونت" in authority or "رییس" in authority or "رئیس" in authority:
        return HierarchyLevel.EXECUTIVE_REGULATION

    if title.startswith("بخشنامه"):
        return HierarchyLevel.CIRCULAR
    if document_type == DocumentType.CIRCULAR:
        return HierarchyLevel.CIRCULAR
    if document_type in {
        DocumentType.REGULATION,
        DocumentType.RESOLUTION,
        DocumentType.EXECUTIVE_RESOLUTION,
        DocumentType.BYLAW,
        DocumentType.DECREE,
    }:
        return HierarchyLevel.EXECUTIVE_REGULATION
    if document_type == DocumentType.LAW:
        return HierarchyLevel.ORDINARY_LAW
    return HierarchyLevel.ORDINARY_LAW


def classify_document(metadata: Dict[str, Any]) -> Dict[str, Any]:
    title = metadata["title"]
    category = metadata["category"]
    searchable_text = " ".join([title, category])

    document_type = DocumentType.OTHER
    for candidate_type, keywords in DOCUMENT_TYPE_RULES:
        if any(keyword in searchable_text for keyword in keywords):
            document_type = candidate_type
            break

    status = DocumentStatus.UNKNOWN
    if any(keyword in searchable_text for keyword in ["لغو", "ابطال", "منسوخ", "نامعتبر"]):
        status = DocumentStatus.REPEALED
    elif any(keyword in searchable_text for keyword in ["اصلاح", "اصلاحیه", "اصلاحی", "الحاق"]):
        status = DocumentStatus.AMENDED
    else:
        status = DocumentStatus.ACTIVE

    hierarchy_level = determine_hierarchy(metadata=metadata, document_type=document_type)
    return {
        "document_type": document_type,
        "hierarchy_level": hierarchy_level,
        "status": status,
    }


def normalize_node(node: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "type": normalize_text(node.get("type", "")).lower(),
        "marker": normalize_text(node.get("marker", "")),
        "header": normalize_text(node.get("header", "")),
        "text": normalize_text(node.get("text", "")),
        "children": node.get("children", []),
    }


STRUCTURAL_MARKERS = {
    "کتاب": StructuralType.BOOK,
    "جلد": StructuralType.PART,
    "بخش": StructuralType.PART,
    "فصل": StructuralType.CHAPTER,
    "باب": StructuralType.CHAPTER,
    "قسمت": StructuralType.SECTION,
    "مبحث": StructuralType.SECTION,
    "زیرمبحث": StructuralType.SUBSECTION,
    "زیر بخش": StructuralType.SUBSECTION,
    "زیر‌بخش": StructuralType.SUBSECTION,
    "مقدمه": StructuralType.INTRODUCTION,
    "introduction": StructuralType.INTRODUCTION,
}


def detect_structural_type(node: Dict[str, Any]) -> Optional[str]:
    marker = normalize_text(node.get("marker", ""))
    header = normalize_text(node.get("header", ""))

    for key, structural_type in STRUCTURAL_MARKERS.items():
        if marker == key:
            return structural_type

    combined = f"{marker} {header}".strip()

    for key, structural_type in STRUCTURAL_MARKERS.items():
        if combined.startswith(key):
            return structural_type

    return None


def detect_provision_type(node: Dict[str, Any]) -> str:
    marker = normalize_text(node.get("marker", ""))
    header = normalize_text(node.get("header", ""))

    value = f"{marker} {header}".strip()
    if re.search(r"^ماده\s*(واحده|[0-9۰-۹]+)", value):
        return ProvisionType.ARTICLE
    if re.search(r"^تبصره", value):
        return ProvisionType.NOTE
    if re.match(r"^[الفبپتثجچحخدذرزژسشصضطظعغفقکگلمنوهی]\s*[\)\-ـ]", value):
        return ProvisionType.ITEM
    if re.match(r"^[0-9۰-۹٠-٩]+\s*[\-ـ–—\.]", value):
        return ProvisionType.CLAUSE
    if re.match(r"^[0-9۰-۹٠-٩]+\s*$", value):
        return ProvisionType.CLAUSE

    node_type = normalize_text(node.get("type", "")).lower()

    if node_type == "provision":
        return ProvisionType.OTHER
    return ProvisionType.OTHER


def determine_element_type(node: Dict[str, Any]) -> Tuple[str, Optional[str]]:
    structural_type = detect_structural_type(node)
    if structural_type is not None:
        return ElementType.STRUCTURAL, structural_type
    provision_type = detect_provision_type(node)
    return ElementType.PROVISION, provision_type


def is_empty_node(node: Dict[str, Any]) -> bool:
    header = normalize_text(node.get("header", ""))
    text = normalize_text(node.get("text", ""))

    return not header and not text


def extract_nodes(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    structure = data.get("structure", [])
    if isinstance(structure, dict):
        structure = [structure]
    if not isinstance(structure, list):
        raise ValueError("structure must be a list after JSON repair")
    result = []
    for raw_node in structure:
        if not isinstance(raw_node, dict):
            continue
        node = normalize_node(raw_node)
        if is_empty_node(node):
            continue
        result.append(node)
    return result


PERSIAN_LETTERS = "الفبپتثجچحخدذرزژسشصضطظعغفقکگلمنوهی"


def extract_version_date(text: str, default_date: str) -> str:
    if not text:
        return default_date
    match = re.search(r"\[[^\]]*?([0-9]{4}/[0-9]{2}/[0-9]{2})[^\]]*?\]", text)
    if match:
        return match.group(1)
    return default_date


def extract_provision_number(header: str, provision_type: str) -> str:
    header = normalize_text(header)
    if not header:
        return ""
    if provision_type == ProvisionType.ARTICLE:
        match = re.search(r"ماده\s*(?:واحده|([0-9]+))", header)
        if match:
            if match.group(1):
                return match.group(1)
            return "واحده"

    elif provision_type == ProvisionType.NOTE:
        match = re.search(r"تبصره\s*([0-9]+)?", header)
        if match and match.group(1):
            return match.group(1)
        return ""

    elif provision_type == ProvisionType.CLAUSE:
        match = re.match(r"([0-9]+)", header)
        if match:
            return match.group(1)

    elif provision_type == ProvisionType.ITEM:
        match = re.match(rf"([{PERSIAN_LETTERS}])", header)
        if match:
            return match.group(1)
    return ""


def extract_provision_title(header: str, provision_type: str) -> str:
    header = normalize_text(header)
    if not header:
        return ""
    if provision_type == ProvisionType.ARTICLE:
        value = re.sub(r"^ماده\s*(?:واحده|[0-9]+)\s*[ـ\-–—]?\s*", "", header)
        return value.strip()
    if provision_type == ProvisionType.NOTE:
        value = re.sub(r"^تبصره\s*[0-9]*\s*[ـ\-–—]?\s*", "", header)
        return value.strip()
    return ""


def find_in_stack(stack: List[Dict[str, Any]], predicate) -> int:
    for i in range(len(stack) - 1, -1, -1):
        if predicate(stack[i]):
            return i
    return -1


def is_same_type(stack_item: Dict[str, Any], type: str) -> bool:
    return stack_item["subtype"] == type


def determine_parent(stack: List[Dict[str, Any]], element_type: str, subtype: str) -> Optional[LegalElement]:
    if not stack:
        return None
    same_index = find_in_stack(stack, lambda item: is_same_type(item, subtype))
    if same_index != -1:
        del stack[same_index:]
    return stack[-1]["element"] if stack else None


def create_structural_element(
    document: LegalDocument,
    parent: Optional[LegalElement],
    order: int,
    subtype: str,
    node: Dict[str, Any],
) -> LegalElement:
    element = LegalElement.objects.create(
        document=document,
        parent=parent,
        element_type=ElementType.STRUCTURAL,
        order=order,
    )
    header = normalize_text(node.get("header", ""))
    marker = normalize_text(node.get("marker", ""))
    title = header
    number = ""
    if marker:
        number_match = re.search(r"(?:اول|دوم|سوم|چهارم|پنجم|ششم|هفتم|هشتم|نهم|دهم|[0-9]+|[۰-۹]+)", header)
        if number_match:
            number = normalise_digits(number_match.group(0))

    StructuralElement.objects.create(element=element, structural_type=subtype, title=title, number=number)
    return element, order + 1


def create_provision_element(
    document: LegalDocument,
    parent: Optional[LegalElement],
    order: int,
    subtype: str,
    node: Dict[str, Any],
) -> LegalElement:
    header = normalize_text(node.get("header", ""))
    text = normalize_text(node.get("text", ""))
    if not text:
        return None, order
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return None, order

    if re.search(
        r"\[\s*(?:اصلاحی|اصلاحیه|الحاقی)?\s*"
        r"[0-9۰-۹٠-٩]{4}\s*/\s*"
        r"[0-9۰-۹٠-٩]{1,2}\s*/\s*"
        r"[0-9۰-۹٠-٩]{1,2}\s*\]",
        lines[0],
    ):
        version_marker = lines[0]
        if len(lines) >= 2:
            lines = lines[1:]
        else:  # This means the provision has no text other than that
            return None, order
        version_date = extract_version_date(version_marker, document.approval_date)

    else:
        version_date = document.approval_date

    main_text = lines[0]
    extra_text = "\n".join(lines[1:])
    number = extract_provision_number(header, subtype)
    title = extract_provision_title(header, subtype)
    element = LegalElement.objects.create(
        document=document,
        parent=parent,
        element_type=ElementType.PROVISION,
        order=order,
    )
    provision = LegalProvision.objects.create(
        element=element,
        provision_type=subtype,
        number=number,
        title=title,
        text=main_text,
    )
    LegalVersion.objects.create(provision=provision, version_date=version_date, text=main_text)
    new_order = order + 1
    if extra_text:
        other_element = LegalElement.objects.create(
            document=document,
            parent=parent,
            element_type=ElementType.PROVISION,
            order=new_order,
        )
        other_provision = LegalProvision.objects.create(
            element=other_element,
            provision_type=ProvisionType.OTHER,
            number="",
            title="متفرقه",
            text=extra_text,
        )
        LegalVersion.objects.create(
            provision=other_provision,
            version_date=document.approval_date,
            text=extra_text,
        )
        new_order += 1
    return element, new_order


def process_node(
    document: LegalDocument,
    node: Dict[str, Any],
    stack: List[Dict[str, Any]],
    order: int,
) -> LegalElement:
    element_type, subtype = determine_element_type(node)
    if subtype is None:
        subtype = StructuralType.OTHER if element_type == ElementType.STRUCTURAL else ProvisionType.OTHER
    parent = determine_parent(stack=stack, element_type=element_type, subtype=subtype)
    if element_type == ElementType.STRUCTURAL:
        element, new_order = create_structural_element(document=document, parent=parent, order=order, subtype=subtype, node=node)
    else:
        element, new_order = create_provision_element(document=document, parent=parent, order=order, subtype=subtype, node=node)
    if element is not None:
        stack.append(
            {
                "element": element,
                "element_type": element_type,
                "subtype": subtype,
            }
        )

    return element, new_order


def process_nodes(document: LegalDocument, nodes: List[Dict[str, Any]]) -> None:
    stack: List[Dict[str, Any]] = []
    order = 0
    for node in nodes:
        element, new_order = process_node(document=document, node=node, stack=stack, order=order)
        order = new_order


def create_or_get_entity(title: str) -> LegalEntity:
    title = normalize_text(title)
    entity, _ = LegalEntity.objects.get_or_create(canonical_title=title, defaults={"entity_type": "legal_document"})
    return entity


def create_legal_document(metadata: Dict[str, Any], classification: Dict[str, Any]) -> LegalDocument:
    title = metadata["title"]
    entity = create_or_get_entity(title)
    return LegalDocument.objects.create(
        entity=entity,
        title=title,
        document_id=metadata["id"],
        document_type=classification["document_type"],
        hierarchy_level=classification["hierarchy_level"],
        issuing_authority=metadata["issuing_authority"],
        approval_date=metadata["approval_date"],
        publication_date=metadata["publication_date"],
        status=classification["status"],
    )


@transaction.atomic
def import_document(data: Dict[str, Any], source_document: Optional[SourceDocument] = None) -> Optional[LegalDocument]:
    metadata = extract_document_metadata(data)
    if not metadata["is_iranian"]:
        return None
    classification = classify_document(metadata)
    nodes = extract_nodes(data)
    document = create_legal_document(metadata, classification)
    if source_document is not None:
        DocumentSource.objects.create(document=document, source_document=source_document, is_primary=True)
    process_nodes(document=document, nodes=nodes)
    return document
