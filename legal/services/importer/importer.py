import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from django.db import transaction
from ..utility.normalizer import normalize_text
from ...models import (
    LegalVersion, DocumentType, DocumentStatus, ElementType, StructuralType,
    ProvisionType, LegalEntity, SourceDocument, LegalDocument, DocumentSource,
    LegalElement, StructuralElement,
)


def read_file(path: str | Path) -> Dict[str, Any]:
    path = Path(path)
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Invalid document root in {path}")
    return data


def check_non_iranian(value: str) -> bool:
    return "قانون خارجی" in normalize_text(value)


def get_issuing_authority(value: str) -> str:
    return normalize_text(value).split("-")[0].strip()


def extract_document_metadata(data: Dict[str, Any]) -> Dict[str, Any]:
    category = data.get("category", "")
    return {
        "id": normalize_text(data.get("id", "")),
        "title": normalize_text(data.get("title", "")),
        "url": normalize_text(data.get("url", "")),
        "approval_date": normalize_text(data.get("approval_date", "")),
        "category": normalize_text(category),
        "publication_date": normalize_text(data.get("publication_date")),
        "is_iranian": not check_non_iranian(category),
        "issuing_authority": get_issuing_authority(category),
    }


DOCUMENT_TYPE_RULES = [
    (DocumentType.EXECUTIVE_RESOLUTION, ["تصویب نامه اجرایی", "تصویب‌نامه اجرایی"]),
    (DocumentType.RESOLUTION, ["تصویب نامه", "تصویب‌نامه", "مصوبه", "مصوبات"]),
    (DocumentType.BYLAW, ["اساسنامه"]),
    (DocumentType.REGULATION, ["آیین نامه", "آیین‌نامه"]),
    (DocumentType.CIRCULAR, ["بخشنامه"]),
    (DocumentType.DECREE, ["دستورالعمل", "ابلاغیه", "دستور ابلاغ"]),
    (DocumentType.LAW, ["قانون"]),
]


def determine_hierarchy(metadata: Dict[str, Any], document_type: str) -> str:
    title = normalize_text(metadata["title"])
    authority = normalize_text(metadata["issuing_authority"])
    if title.startswith("قانون اساسی"):
        return HierarchyLevel.CONSTITUTION
    if "مجلس" in authority or "مجمع تشخیص" in authority:
        return HierarchyLevel.ORDINARY_LAW
    if any(x in authority for x in ["هیئت وزیران", "وزیر", "وزارت", "سازمان", "معاونت", "رییس", "رئیس"]):
        return HierarchyLevel.EXECUTIVE_REGULATION
    if title.startswith("بخشنامه") or document_type == DocumentType.CIRCULAR:
        return HierarchyLevel.CIRCULAR
    if document_type in {
        DocumentType.REGULATION, DocumentType.RESOLUTION,
        DocumentType.EXECUTIVE_RESOLUTION, DocumentType.BYLAW,
        DocumentType.DECREE,
    }:
        return HierarchyLevel.EXECUTIVE_REGULATION
    return HierarchyLevel.ORDINARY_LAW


def classify_document(metadata: Dict[str, Any]) -> Dict[str, Any]:
    title = metadata["title"]
    category = metadata["category"]
    searchable_text = f"{title} {category}"
    document_type = DocumentType.OTHER

    for candidate_type, keywords in DOCUMENT_TYPE_RULES:
        if any(keyword in searchable_text for keyword in keywords):
            document_type = candidate_type
            break

    if any(x in searchable_text for x in ["لغو", "ابطال", "منسوخ", "نامعتبر"]):
        status = DocumentStatus.REPEALED
    elif any(x in searchable_text for x in ["اصلاح", "اصلاحیه", "اصلاحی", "الحاق"]):
        status = DocumentStatus.AMENDED
    else:
        status = DocumentStatus.ACTIVE

    return {
        "document_type": document_type,
        "hierarchy_level": determine_hierarchy(metadata, document_type),
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


def detect_structural_type(node: Dict[str, Any]):
    node_type = normalize_text(node.get("type", "")).lower()
    if node_type in {"unscoped", "introduction"}:
        return StructuralType.OTHER

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
    marker = normalize_text(node.get("marker", "")).strip().lower()
    header = normalize_text(node.get("header", "")).strip()

    marker_types = {
        "ماده": ProvisionType.ARTICLE,
        "تبصره": ProvisionType.NOTE,
        "بند": ProvisionType.CLAUSE,
        "جزء": ProvisionType.SUBCLAUSE,
        "زیر بند": ProvisionType.SUBCLAUSE,
        "زیر‌بند": ProvisionType.SUBCLAUSE,
        "مورد": ProvisionType.ITEM,
        "قسمت": ProvisionType.ITEM,
    }

    if marker in marker_types:
        return marker_types[marker]
    if "ماده" in header:
        return ProvisionType.ARTICLE
    if "تبصره" in header:
        return ProvisionType.NOTE
    if "بند" in header:
        return ProvisionType.CLAUSE
    if normalize_text(node.get("type", "")).lower() == "provision":
        return ProvisionType.OTHER
    return ProvisionType.OTHER


def determine_element_type(node: Dict[str, Any]) -> Tuple[str, Optional[str]]:
    structural_type = detect_structural_type(node)
    if structural_type is not None:
        return ElementType.STRUCTURAL, structural_type
    return ElementType.PROVISION, detect_provision_type(node)


def is_empty_node(node: Dict[str, Any]) -> bool:
    return not normalize_text(node.get("header", "")) and not normalize_text(node.get("text", ""))


def extract_nodes(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    structure = data.get("structure", [])
    if isinstance(structure, dict):
        structure = [structure]
    if not isinstance(structure, list):
        raise ValueError("structure must be a list after JSON repair")

    result = []
    for raw_node in structure:
        if isinstance(raw_node, dict):
            node = normalize_node(raw_node)
            if not is_empty_node(node):
                result.append(node)
    return result


def extract_version_date(text: str, default_date: str) -> str:
    if not text:
        return default_date
    match = re.search(r"\[[^\]]*?([0-9]{4}/[0-9]{2}/[0-9]{2})[^\]]*?\]", text)
    return match.group(1) if match else default_date


def clean_extracted_number(value: str) -> str:
    value = normalize_text(value).strip()
    value = re.sub(r'^[\s\-–—ـ:،,;."\'«»‹›<>\[\](){}]+', "", value)
    value = re.sub(r'[\s\-–—ـ:،,;."\'«»‹›<>\[\](){}]+$', "", value)
    return value.strip()


def extract_marker_number(header: str, marker: str) -> str:
    header = normalize_text(header).strip()
    marker = normalize_text(marker).strip()
    if not header or not marker:
        return ""

    match = re.search(re.escape(marker), header)
    if not match:
        return ""

    before = header[:match.start()]
    after = header[match.end():]

    for value in [
        re.split(r"[-–—ـ]", before)[-1],
        re.split(r"[-–—ـ]", after)[-1],
        re.split(r"[-–—ـ]", after)[0],
    ]:
        value = clean_extracted_number(value)
        if value:
            return value

    return ""


def extract_provision_number(header: str, provision_type: str, marker: str = "") -> str:
    header = normalize_text(header)
    if not header:
        return ""

    if marker:
        number = extract_marker_number(header, marker)
        if number:
            return number

    if provision_type == ProvisionType.ARTICLE:
        match = re.search(r"ماده\s*(?:واحده|([0-9۰-۹٠-٩]+))", header)
        return match.group(1) if match and match.group(1) else ("واحده" if match else "")

    if provision_type == ProvisionType.NOTE:
        match = re.search(r"تبصره\s*([0-9۰-۹٠-٩]+)?", header)
        return match.group(1) if match and match.group(1) else ""

    if provision_type == ProvisionType.CLAUSE:
        match = re.match(r"([0-9۰-۹٠-٩]+)", header)
        return match.group(1) if match else ""

    if provision_type == ProvisionType.ITEM:
        match = re.match(rf"([{PERSIAN_LETTERS}])", header)
        return match.group(1) if match else ""

    return ""


def extract_provision_title(header: str, provision_type: str, marker: str = "") -> str:
    header = normalize_text(header)
    if not header:
        return ""

    if marker:
        match = re.search(re.escape(normalize_text(marker)), header)
        if match:
            return re.sub(
                r"^\s*[-–—ـ:،,;\"'«»‹›<>\[\](){}]*\s*",
                "",
                header[match.end():],
            ).strip()

    if provision_type == ProvisionType.ARTICLE:
        return re.sub(r"^ماده\s*(?:واحده|[0-9۰-۹٠-٩]+)\s*[ـ\-–—]?\s*", "", header).strip()

    if provision_type == ProvisionType.NOTE:
        return re.sub(r"^تبصره\s*[0-9۰-۹٠-٩]*\s*[ـ\-–—]?\s*", "", header).strip()

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

    same_index = find_in_stack(
        stack,
        lambda item: is_same_type(item, subtype),
    )

    if same_index != -1:
        del stack[same_index:]

    return stack[-1]["element"] if stack else None


def create_structural_element(document, parent, order, subtype, node):
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
        match = re.search(
            r"(?:اول|دوم|سوم|چهارم|پنجم|ششم|هفتم|هشتم|نهم|دهم|[0-9۰-۹]+)",
            header,
        )
        if match:
            number = match.group(0)

    StructuralElement.objects.create(
        element=element,
        structural_type=subtype,
        title=title,
        number=number,
    )

    new_order = order + 1
    text = normalize_text(node.get("text", ""))

    if text:
        provision_element = LegalElement.objects.create(
            document=document,
            parent=element,
            element_type=ElementType.PROVISION,
            order=new_order,
        )
        provision = LegalProvision.objects.create(
            element=provision_element,
            provision_type=ProvisionType.OTHER,
            number="",
            title=header,
            text=text,
        )
        LegalVersion.objects.create(provision=provision, text=text)
        new_order += 1

    return element, new_order


def create_provision_element(document, parent, order, subtype, node):
    header = normalize_text(node.get("header", ""))
    marker = normalize_text(node.get("marker", ""))
    text = normalize_text(node.get("text", ""))

    if not text and not header:
        return None, order

    lines = [line.strip() for line in text.splitlines() if line.strip()] if text else []
    main_text = lines[0] if lines else ""
    extra_text = "\n".join(lines[1:]) if len(lines) > 1 else ""

    number = extract_provision_number(header, subtype, marker)
    title = extract_provision_title(header, subtype, marker)

    if not main_text:
        main_text = header

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

    LegalVersion.objects.create(provision=provision, text=main_text)

    new_order = order + 1

    if extra_text:
        other_element = LegalElement.objects.create(
            document=document,
            parent=element,
            element_type=ElementType.PROVISION,
            order=new_order,
        )
        other_provision = LegalProvision.objects.create(
            element=other_element,
            provision_type=ProvisionType.OTHER,
            title="متفرقه",
            text=extra_text,
        )
        LegalVersion.objects.create(provision=other_provision, text=extra_text)
        new_order += 1

    return element, new_order


def process_node(document, node, stack, order):
    element_type, subtype = determine_element_type(node)

    if subtype is None:
        subtype = StructuralType.OTHER if element_type == ElementType.STRUCTURAL else ProvisionType.OTHER

    parent = determine_parent(stack, element_type, subtype)

    if element_type == ElementType.STRUCTURAL:
        element, new_order = create_structural_element(document, parent, order, subtype, node)
    else:
        element, new_order = create_provision_element(document, parent, order, subtype, node)

    if element is not None:
        stack.append({
            "element": element,
            "element_type": element_type,
            "subtype": subtype,
        })

    return element, new_order


def process_nodes(document, nodes):
    stack = []
    order = 0

    for node in nodes:
        _, order = process_node(document, node, stack, order)


def create_or_get_entity(title: str) -> LegalEntity:
    title = normalize_text(title)
    entity, _ = LegalEntity.objects.get_or_create(
        canonical_title=title,
        defaults={"entity_type": "legal_document"},
    )
    return entity


def create_legal_document(metadata, classification):
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
def import_document(data, source_document=None):
    metadata = extract_document_metadata(data)

    if not metadata["is_iranian"]:
        return None

    classification = classify_document(metadata)
    nodes = extract_nodes(data)
    document = create_legal_document(metadata, classification)

    if source_document is not None:
        DocumentSource.objects.create(
            document=document,
            source_document=source_document,
            is_primary=True,
        )

    process_nodes(document, nodes)
    return document