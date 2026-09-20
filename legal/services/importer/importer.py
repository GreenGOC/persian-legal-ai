import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from django.db import transaction
from ..utility.normalizer import normalize_text
from ...models import (
    LegalVersion, DocumentType, DocumentStatus, ElementType, StructuralType,
    ProvisionType, LegalEntity, SourceDocument, LegalDocument, ProcessingStatus, Source,
    LegalElement, StructuralElement, LegalProvision, HierarchyLevel
)

ANNOTATION_PATTERN = r"\[([^\]]*)\]"
PERSIAN_LETTERS = "الفبپتثجچحخدذرزژسشصضطظعغفقکگلمنوهی"
PROVISION_SEPARATORS = r"[-–—ـ:؛;|/\\(){}\[\]<>«»\"']+"
PROVISION_MARKERS = {
    "ماده": ProvisionType.ARTICLE,
    "تبصره": ProvisionType.NOTE,
    "بند": ProvisionType.CLAUSE,
    "جزء": ProvisionType.SUBCLAUSE,
    "زیر بند": ProvisionType.SUBCLAUSE,
    "زیر‌بند": ProvisionType.SUBCLAUSE,
    "مورد": ProvisionType.ITEM,
    "قسمت": ProvisionType.ITEM,
}

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
        "id": normalize_text(data.get("id", "")) or None,
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
        DocumentType.REGULATION,
        DocumentType.RESOLUTION,
        DocumentType.EXECUTIVE_RESOLUTION,
        DocumentType.BYLAW,
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

def clean_extracted_number(value: str) -> str:
    value = normalize_text(value).strip()
    value = re.sub(r'^[\s\-–—ـ:،,;."\'«»‹›<>\[\](){}]+', "", value)
    value = re.sub(r'[\s\-–—ـ:،,;."\'«»‹›<>\[\](){}]+$', "", value)
    return value.strip()

def clean_extracted_text(value: str) -> str:
    value = normalize_text(value).strip()
    value = re.sub(r'^[\s\-–—ـ:؛;,."\'«»‹›<>\[\](){}]+', "", value)
    return value.strip()

def parse_numbered_provision_prefix(value: str):
    value = normalize_text(value).strip()
    if not value:
        return None

    pattern = (
        rf"^(?P<number>[۰-۹0-9]+|[{PERSIAN_LETTERS}])"
        rf"\s*"
        rf"(?P<separator>[-–—ـ:؛;.)|/\\()\[\]<>«»\"']+)"
        rf"\s*"
        rf"(?P<title>[^\r\n]*)")
    match = re.match(pattern, value)
    if not match:
        return None

    number = clean_extracted_number(match.group("number") or "")
    title = clean_extracted_text(match.group("title") or "")
    if not number:
        return None

    return {
        "type": ProvisionType.CLAUSE,
        "marker": "بند",
        "number": number,
        "title": title,
    }

def parse_provision_prefix(value: str):
    value = normalize_text(value).strip()
    if not value:
        return None

    value = re.sub(r"^[\s\"'«»‹›<>\[\]{}()]+", "", value)
    marker_pattern = "|".join(sorted(map(re.escape, PROVISION_MARKERS), key=len, reverse=True))
    pattern = (
        rf"^(?P<marker>{marker_pattern})"
        rf"\s*"
        rf"(?P<number>واحده|[۰-۹0-9]+|[{PERSIAN_LETTERS}])?"
        rf"\s*"
        rf"(?P<separator>{PROVISION_SEPARATORS})"
        rf"\s*"
        rf"(?P<title>[^\r\n]*)")

    match = re.match(pattern, value)
    if not match:
        return None

    marker = normalize_text(match.group("marker"))
    number = clean_extracted_number(match.group("number") or "")
    title = clean_extracted_text(match.group("title") or "")
    provision_type = PROVISION_MARKERS.get(marker)
    if not provision_type:
        return None

    return {
        "type": provision_type,
        "marker": marker,
        "number": number,
        "title": title,
    }

def extract_from_text(text: str):
    text = normalize_text(text).lstrip()
    if not text:
        return None

    return parse_provision_prefix(text)

def detect_provision_type(node: Dict[str, Any]) -> str:
    marker = normalize_text(node.get("marker", "")).strip()
    header = normalize_text(node.get("header", "")).strip()
    if marker in PROVISION_MARKERS:
        return PROVISION_MARKERS[marker]

    numbered_result = parse_numbered_provision_prefix(header)
    if numbered_result:
        return ProvisionType.CLAUSE

    header_result = parse_provision_prefix(header)
    if header_result:
        return header_result["type"]

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

def clean_line_edges(value: str) -> str:
    value = value.strip()
    value = re.sub(r'^[\s\-–—ـ:؛;,."\'«»‹›<>\[\](){}]+', "",  value)
    value = re.sub(r'[\s\-–—ـ:؛;,."\'«»‹›<>\[\](){}]+$', "", value)
    return value.strip()

def extract_version_date(text: str, default_date: str) -> str:
    if not text:
        return default_date

    text = normalize_text(text)
    lines = text.splitlines()
    while lines and not lines[0].strip():
        lines = lines[1:]

    if not lines:
        return default_date

    first_line = lines[0].strip()
    annotations = re.findall(ANNOTATION_PATTERN, first_line)
    version_date = default_date
    for annotation in annotations:
        annotation = normalize_text(annotation).strip()
        date_match = re.search(r"([0-9۰-۹٠-٩]{4}/[0-9۰-۹٠-٩]{1,2}/[0-9۰-۹٠-٩]{1,2})", annotation)
        if not date_match:
            continue

        if re.search(r"منسوخ|نسخ|حذف|لغو|ملغی|باطل|ابطال", annotation):
            version_date = default_date
        else:
            version_date = date_match.group(1)

    return version_date


def extract_version_text(text: str) -> Tuple[str, str, str]:
    text = normalize_text(text)
    if not text:
        return "", "", ""

    lines = text.splitlines()
    while lines and not lines[0].strip():
        lines = lines[1:]

    if not lines:
        return "", "", ""

    first_line = lines[0].strip()
    annotations = re.findall(ANNOTATION_PATTERN, first_line)
    title = " ".join(normalize_text(annotation).strip() for annotation in annotations if normalize_text(annotation).strip())
    first_line = re.sub(ANNOTATION_PATTERN, "", first_line)
    first_line = clean_line_edges(first_line)
    cleaned_lines = []
    if first_line:
        cleaned_lines.append(first_line)

    for line in lines[1:]:
        line = line.strip()
        if not line:
            continue

        line = clean_line_edges(line)
        if line:
            cleaned_lines.append(line)

    if not cleaned_lines:
        return "", "", title

    main_text = cleaned_lines[0]
    extra_text = "\n".join(cleaned_lines[1:])
    return main_text, extra_text, title

def extract_marker_number(header: str, marker: str) -> str:
    header = normalize_text(header).strip()
    marker = normalize_text(marker).strip()
    if not header or not marker:
        return ""

    if marker not in PROVISION_MARKERS:
        return ""

    result = parse_provision_prefix(header)
    if result and result["marker"] == marker:
        return result["number"]

    pattern = (
        rf"^{re.escape(marker)}\s*"
        rf"(واحده|[۰-۹0-9]+|[{PERSIAN_LETTERS}])"
        rf"(?:\s|$)")

    match = re.match(pattern, header)
    if not match:
        return ""

    return clean_extracted_number(match.group(1))


def extract_provision_number(header: str, provision_type: str, marker: str = "", text: str = "") -> str:
    header = normalize_text(header).strip()
    if marker:
        number = extract_marker_number(header, marker)
        if number:
            return number

    if provision_type == ProvisionType.CLAUSE:
        numbered_result = parse_numbered_provision_prefix(header)
        if numbered_result:
            return numbered_result["number"]

    header_result = parse_provision_prefix(header)
    if header_result and header_result["number"]:
        return header_result["number"]

    if not header or provision_type == ProvisionType.OTHER:
        text_result = extract_from_text(text)
        if text_result and text_result["number"]:
            return text_result["number"]

        numbered_result = parse_numbered_provision_prefix(text)
        if numbered_result:
            return numbered_result["number"]

    if provision_type == ProvisionType.ARTICLE:
        match = re.match(r"^ماده\s*(واحده|[0-9۰-۹٠-٩]+)(?:\s|$)", header)
        return match.group(1) if match else ""

    if provision_type == ProvisionType.NOTE:
        match = re.match(r"^تبصره\s*([0-9۰-۹٠-٩]+)?(?:\s|$)", header)
        return match.group(1) if match and match.group(1) else ""

    if provision_type == ProvisionType.CLAUSE:
        match = re.match(rf"^([{PERSIAN_LETTERS}]|[0-9۰-۹٠-٩]+)\s*[-–—ـ:؛;.)|/\\()\[\]<>«»\"']+", header)
        return match.group(1) if match else ""

    if provision_type == ProvisionType.ITEM:
        match = re.match(rf"^([{PERSIAN_LETTERS}])(?:\s|$)", header)
        return match.group(1) if match else ""

    return ""


def extract_provision_title(header: str, provision_type: str, marker: str = "", text: str = "") -> str:
    header = normalize_text(header).strip()
    if provision_type == ProvisionType.CLAUSE:
        numbered_result = parse_numbered_provision_prefix(header)
        if numbered_result:
            return numbered_result["title"]

    header_result = parse_provision_prefix(header)
    if header_result and header_result["title"]:
        return header_result["title"]

    if marker:
        marker_pattern = rf"^{re.escape(normalize_text(marker))}"
        match = re.match(marker_pattern, header)

        if match:
            remainder = header[match.end():].strip()
            remainder = re.sub(rf"^(?:واحده|[۰-۹0-9]+|[{PERSIAN_LETTERS}])\s*", "", remainder)
            remainder = re.sub(rf"^{PROVISION_SEPARATORS}\s*", "", remainder).strip()
            if remainder:
                return remainder

    if not header or provision_type == ProvisionType.OTHER:
        text_result = extract_from_text(text)
        if text_result and text_result["title"]:
            return text_result["title"]

        numbered_result = parse_numbered_provision_prefix(text)
        if numbered_result:
            return numbered_result["title"]

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

    same_index = find_in_stack(stack, lambda item: is_same_type(item, subtype))
    if same_index != -1:
        del stack[same_index:]

    return stack[-1]["element"] if stack else None


def create_structural_element(document, parent, order, subtype, node):
    element = LegalElement.objects.create(document=document, parent=parent, element_type=ElementType.STRUCTURAL, order=order)
    header = normalize_text(node.get("header", ""))
    marker = normalize_text(node.get("marker", ""))
    title = header
    number = ""
    if marker:
        match = re.search(r"(?:اول|دوم|سوم|چهارم|پنجم|ششم|هفتم|هشتم|نهم|دهم|[0-9۰-۹]+)", header)
        if match:
            number = match.group(0)

    StructuralElement.objects.create(element=element, structural_type=subtype, title=title, number=number)
    new_order = order + 1
    text = normalize_text(node.get("text", ""))
    if text:
        provision_element = LegalElement.objects.create(document=document, parent=element, element_type=ElementType.PROVISION, order=new_order)
        provision = LegalProvision.objects.create(element=provision_element, provision_type=ProvisionType.OTHER, number="", title=header, text=text)
        LegalVersion.objects.create(provision=provision, text=text)
        new_order += 1

    return element, new_order


def create_provision_element(document, parent, order, subtype, node, default_date=""):
    header = normalize_text(node.get("header", "")).strip()
    marker = normalize_text(node.get("marker", "")).strip()
    text = normalize_text(node.get("text", "")).strip()

    if not text and not header:
        return None, order

    main_text, extra_text, version_title = extract_version_text(text)
    text_result = None
    if subtype == ProvisionType.OTHER or not header:
        text_result = extract_from_text(main_text)
        if not text_result:
            text_result = parse_numbered_provision_prefix(main_text)

    if subtype == ProvisionType.OTHER and text_result:
        subtype = text_result["type"]

    number = extract_provision_number(header, subtype, marker, main_text)
    if not number and text_result:
        number = text_result["number"]

    title = version_title
    if text_result and not title:
        title = text_result["title"]

    if text_result and main_text:
        if text_result["marker"] == "بند" and not main_text.startswith("بند"):
            prefix_pattern = (
                rf"^{re.escape(text_result['number'])}"
                rf"\s*"
                rf"{PROVISION_SEPARATORS}"
                rf"\s*")
        else:
            prefix_pattern = (
                rf"^(?:{re.escape(text_result['marker'])}\s*)?"
                rf"(?:{re.escape(text_result['number'])}\s*)?"
                rf"{PROVISION_SEPARATORS}"
                rf"\s*")

        main_text = re.sub(prefix_pattern, "", main_text, count=1).strip()
    if not main_text:
        main_text = text or header

    element = LegalElement.objects.create(document=document, parent=parent, element_type=ElementType.PROVISION, order=order)
    provision = LegalProvision.objects.create(element=element, provision_type=subtype, number=number, title=title, text=main_text)
    version_date = extract_version_date(text, default_date)
    LegalVersion.objects.create(provision=provision, text=main_text, version_date=version_date)
    new_order = order + 1
    if extra_text:
        other_element = LegalElement.objects.create(document=document, parent=element, element_type=ElementType.PROVISION, order=new_order)
        other_provision = LegalProvision.objects.create(element=other_element, provision_type=ProvisionType.OTHER, title="متفرقه", text=extra_text)
        LegalVersion.objects.create(provision=other_provision, text=extra_text)
        new_order += 1
        
    return element, new_order


def process_node(document, node, stack, order, approval_date):
    element_type, subtype = determine_element_type(node)
    if subtype is None:
        subtype = StructuralType.OTHER if element_type == ElementType.STRUCTURAL else ProvisionType.OTHER

    parent = determine_parent(stack, element_type, subtype)
    if element_type == ElementType.STRUCTURAL:
        element, new_order = create_structural_element(document, parent, order, subtype, node)
    else:
        element, new_order = create_provision_element(document, parent, order, subtype, node, approval_date)

    if element is not None:
        stack.append({
                "element": element,
                "element_type": element_type,
                "subtype": subtype,
            })
    return element, new_order

def process_nodes(document, nodes, approval_date):
    stack = []
    order = 0
    for node in nodes:
        _, order = process_node(document, node, stack, order, approval_date)

def create_or_get_entity(title: str) -> LegalEntity:
    title = normalize_text(title)
    entity, _ = LegalEntity.objects.get_or_create(canonical_title=title, defaults={"entity_type": "legal_document"})
    return entity

def create_legal_document(metadata, classification, source_document):
    title = metadata["title"] or (source_document.title if source_document else "")
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
def import_document(data, source_id):
    metadata = extract_document_metadata(data)
    if not metadata["is_iranian"]:
        return None

    source_document = SourceDocument.objects.create(source=Source.NEZAMAT, source_id=str(source_id), url=metadata["url"], title=metadata["title"], processing_status=ProcessingStatus.PROCESSING)
    classification = classify_document(metadata)
    nodes = extract_nodes(data)
    document = create_legal_document(metadata, classification, source_document)
    process_nodes(document, nodes, metadata["approval_date"])
    source_document.processing_status = ProcessingStatus.PROCESSED
    source_document.save(update_fields=["processing_status"])
    return document