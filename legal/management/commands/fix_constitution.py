from ...services.utility.normalizer import normalize_text
import json
import re
from pathlib import Path
from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand
from django.db import transaction

from legal.models import (
    LegalDocument,
    LegalElement,
    LegalProvision,
    LegalVersion,
    ElementType,
    ProvisionType,
    VersionStatus,
    HierarchyLevel,
)

PERSIAN_NUMBERS = {
    "صفر": 0,
    "یک": 1,
    "دو": 2,
    "سه": 3,
    "چهار": 4,
    "پنج": 5,
    "شش": 6,
    "هفت": 7,
    "هشت": 8,
    "نه": 9,
    "ده": 10,
    "یازده": 11,
    "دوازده": 12,
    "سیزده": 13,
    "چهارده": 14,
    "پانزده": 15,
    "شانزده": 16,
    "هفده": 17,
    "هجده": 18,
    "نوزده": 19,
    "بیست": 20,
    "سی": 30,
    "چهل": 40,
    "پنجاه": 50,
    "شصت": 60,
    "هفتاد": 70,
    "هشتاد": 80,
    "نود": 90,
    "صد": 100,
    "یکصد": 100,
    "دویست": 200,
    "سیصد": 300,
    "چهارصد": 400,
    "پانصد": 500,
    "ششصد": 600,
    "هفتصد": 700,
    "هشتصد": 800,
    "نهصد": 900,
    "هزار": 1000,
}

ORDINALS = {
    "اول": "یک",
    "دوم": "دو",
    "سوم": "سه",
    "چهارم": "چهار",
    "پنجم": "پنج",
    "ششم": "شش",
    "هفتم": "هفت",
    "هشتم": "هشت",
    "نهم": "نه",
    "دهم": "ده",
    "یازدهم": "یازده",
    "دوازدهم": "دوازده",
    "سیزدهم": "سیزده",
    "چهاردهم": "چهارده",
    "پانزدهم": "پانزده",
    "شانزدهم": "شانزده",
    "هفدهم": "هفده",
    "هجدهم": "هجده",
    "نوزدهم": "نوزده",
    "بیستم": "بیست",
    "سی‌ام": "سی",
    "سی ام": "سی",
    "چهلم": "چهل",
    "پنجاهم": "پنجاه",
    "شصتم": "شصت",
    "هفتادم": "هفتاد",
    "هشتادم": "هشتاد",
    "نودم": "نود",
    "صدم": "صد",
    "یکصدم": "یکصد",
    "دویستم": "دویست",
    "سیصدم": "سیصد",
    "چهارصدم": "چهارصد",
    "پانصدم": "پانصد",
    "ششصدم": "ششصد",
    "هفتصدم": "هفتصد",
    "هشتصدم": "هشتصد",
    "نهصدم": "نهصد",
    "هزارم": "هزار",
}

CURRENT_PRINCIPLE_HEADING_RE = re.compile(
    r"^\s*اصل\s+(.+?)(?:\s*\[\s*(مصوب|اصلاحی)\s*([0-9۰-۹٠-٩]{4})\s*\])?\s*$"
)

HISTORICAL_VERSION_RE = re.compile(
    r"^\s*\[\s*اصل\s+([0-9۰-۹٠-٩]+)\s+(مصوب|اصلاحی)\s+([0-9۰-۹٠-٩]{4})\s*:(.*?)\]\s*$",
    re.DOTALL,
)


def normalize_digits(value: str) -> str:
    return str(value).translate(
        str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    )


def normalize_ordinal_word(word: str) -> str:
    word = normalize_text(word).strip().replace("‌", "")
    if word in ORDINALS:
        return ORDINALS[word]
    if word.endswith("ام"):
        return word[:-2]
    if word.endswith("م") and len(word) > 2:
        return word[:-1]
    return word


def persian_number_to_int(value: str):
    if not value:
        return None
    value = normalize_text(value).strip().replace("‌", "")
    numeric_value = normalize_digits(value)
    if numeric_value.isdigit():
        return int(numeric_value)
    value = value.replace("‌", " ")
    value = re.sub(r"\s+", " ", value).strip()
    tokens = value.split()
    if not tokens:
        return None

    tokens = [normalize_ordinal_word(token) for token in tokens]
    total = 0
    current = 0

    for token in tokens:
        if token == "و":
            continue
        if token not in PERSIAN_NUMBERS:
            return None

        number = PERSIAN_NUMBERS[token]

        if number == 1000:
            if current == 0:
                current = 1
            total += current * 1000
            current = 0
        elif number >= 100:
            if current == 0:
                current = 1
            current *= number
        else:
            current += number

    total += current
    return total if total else None


def extract_first_line(paragraph):
    text = paragraph.get_text("\n", strip=True)
    lines = [
        normalize_text(line).strip()
        for line in text.splitlines()
        if normalize_text(line).strip()
    ]
    return lines[0] if lines else ""


def parse_principle_heading(heading: str):
    heading = normalize_text(heading).strip()
    match = CURRENT_PRINCIPLE_HEADING_RE.match(heading)

    if not match:
        return None

    number = persian_number_to_int(match.group(1))

    if number is None:
        return None

    return {
        "number": number,
        "label": match.group(2),
        "version_date": normalize_digits(match.group(3)) if match.group(3) else "",
    }


def clean_current_principle_text(paragraph, heading: str):
    text = normalize_text(paragraph.get_text(" ", strip=True)).strip()
    heading = normalize_text(heading).strip()

    if text.startswith(heading):
        text = text[len(heading) :].strip()

    return normalize_text(text)


def parse_historical_version(text: str):
    text = normalize_text(text).strip()
    match = HISTORICAL_VERSION_RE.match(text)

    if not match:
        return None

    number = normalize_digits(match.group(1))

    if not number.isdigit():
        return None

    return {
        "number": int(number),
        "label": match.group(2),
        "version_date": normalize_digits(match.group(3)),
        "status": VersionStatus.SUPERSEDED,
        "text": normalize_text(match.group(4)).strip(),
    }


def parse_constitution_html(html_path: str):
    html = Path(html_path).read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")
    paragraphs = soup.find_all("p")
    principles = {}

    for index, paragraph in enumerate(paragraphs):
        raw_text = normalize_text(paragraph.get_text(" ", strip=True)).strip()

        if not raw_text:
            continue

        if re.match(r"^\s*\[\s*اصل\b", raw_text):
            historical = parse_historical_version(raw_text)

            if historical is None:
                print(f"[WARNING] Could not parse historical version: {raw_text[:200]}")
                continue

            number = historical["number"]

            if number not in principles:
                principles[number] = {
                    "provision_type": ProvisionType.CONSTITUTIONAL_PRINCIPLE,
                    "number": str(number),
                    "title": "",
                    "text": "",
                    "versions": [],
                }

            duplicate = any(
                version["version_date"] == historical["version_date"]
                and version["status"] == historical["status"]
                for version in principles[number]["versions"]
            )

            if not duplicate:
                principles[number]["versions"].append(
                    {
                        "text": historical["text"],
                        "version_date": historical["version_date"],
                        "status": historical["status"],
                    }
                )

            continue

        if not re.match(r"^\s*اصل\b", raw_text):
            continue

        heading = extract_first_line(paragraph)
        parsed_heading = parse_principle_heading(heading)

        if parsed_heading is None:
            print(f"[WARNING] Could not parse principle heading: {heading[:200]}")
            continue

        number = parsed_heading["number"]

        if number not in principles:
            principles[number] = {
                "provision_type": ProvisionType.CONSTITUTIONAL_PRINCIPLE,
                "number": str(number),
                "title": "",
                "text": "",
                "versions": [],
            }

        current_text = clean_current_principle_text(paragraph, heading)

        if not current_text and index + 1 < len(paragraphs):
            next_text = normalize_text(
                paragraphs[index + 1].get_text(" ", strip=True)
            ).strip()

            if (
                next_text
                and not re.match(r"^\s*\[\s*اصل\b", next_text)
                and not re.match(r"^\s*اصل\b", next_text)
            ):
                current_text = next_text

        principles[number]["text"] = current_text

        principles[number]["versions"] = [
            version
            for version in principles[number]["versions"]
            if version["status"] != VersionStatus.CURRENT
        ]

        principles[number]["versions"].append(
            {
                "text": current_text,
                "version_date": parsed_heading["version_date"],
                "status": VersionStatus.CURRENT,
            }
        )

    return [principles[number] for number in sorted(principles)]


def delete_existing_constitution_provisions():
    constitution_documents = LegalDocument.objects.filter(
        hierarchy_level=HierarchyLevel.CONSTITUTION
    )

    document_count = constitution_documents.count()

    if document_count == 0:
        print("[INFO] No Constitution LegalDocument found")
        return

    provision_elements = LegalElement.objects.filter(
        document__in=constitution_documents,
        element_type=ElementType.PROVISION,
    )

    element_count = provision_elements.count()

    print(f"[DELETE] Constitution Documents: {document_count}")
    print(f"[DELETE] Constitution Provision Elements: {element_count}")

    provision_elements.delete()


def import_constitution(principles, constitution_document):
    created = 0

    for order, principle in enumerate(principles, start=1):
        element = LegalElement.objects.create(
            document=constitution_document,
            parent=None,
            element_type=ElementType.PROVISION,
            order=order,
        )

        provision = LegalProvision.objects.create(
            element=element,
            provision_type=ProvisionType.CONSTITUTIONAL_PRINCIPLE,
            number=principle["number"],
            title=principle["title"],
            text=principle["text"],
        )

        for version in principle["versions"]:
            LegalVersion.objects.create(
                provision=provision,
                text=version["text"],
                version_date=version["version_date"],
                status=version["status"],
            )

        created += 1
        print(f"[OK] اصل {principle['number']}")

    return created


class Command(BaseCommand):
    help = "Parse Constitution HTML and replace existing Constitution provisions."

    def add_arguments(self, parser):
        parser.add_argument(
            "--input", default="constitution.html", help="Path to Constitution HTML."
        )
        parser.add_argument(
            "--output",
            default="constitution_provisions.json",
            help="Path for intermediate JSON.",
        )
        parser.add_argument(
            "--document-id",
            type=int,
            required=True,
            help="ID of the Constitution LegalDocument.",
        )
        parser.add_argument(
            "--no-db",
            action="store_true",
            help="Only parse HTML and create JSON. Do not modify the database.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        input_path = options["input"]
        output_path = options["output"]
        document_id = options["document_id"]

        self.stdout.write(f"[INFO] Reading: {input_path}")

        principles = parse_constitution_html(input_path)

        self.stdout.write(f"[INFO] Parsed {len(principles)} principles.")

        Path(output_path).write_text(
            json.dumps(principles, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        self.stdout.write(self.style.SUCCESS(f"[OK] JSON written to {output_path}"))

        if options["no_db"]:
            self.stdout.write("[INFO] --no-db specified. Database was not modified.")
            return

        try:
            constitution_document = LegalDocument.objects.get(id=document_id)
        except LegalDocument.DoesNotExist:
            raise ValueError(f"LegalDocument with id={document_id} does not exist.")

        if constitution_document.hierarchy_level != HierarchyLevel.CONSTITUTION:
            raise ValueError(
                "The selected LegalDocument does not have hierarchy_level=CONSTITUTION."
            )

        self.stdout.write(
            f"[INFO] Using Constitution document: {constitution_document.title}"
        )

        delete_existing_constitution_provisions()

        created = import_constitution(principles, constitution_document)

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"Finished. Created {created} constitutional principles."
            )
        )
