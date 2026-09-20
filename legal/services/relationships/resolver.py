import re
from django.db import transaction

from ...models import (
    LegalDocument,
    LegalProvision,
    LegalRelationship,
    RelationshipContext,
    RelationshipType,
    ProvisionType,
)

from ..utility.normalizer import normalize_text


def norm(value):
    return normalize_text(value or "").strip()


def resolve_document(title):
    title = norm(title)

    if not title:
        return None

    documents = LegalDocument.objects.all()

    for document in documents:
        if norm(document.title) == title:
            return document

    return None


# از خاص‌ترین به عمومی‌ترین
PROVISION_PATTERNS = [
    (
        ProvisionType.ITEM,
        r"(?:قسمت)\s*([الفبپتثجچحخدذرزژسشصضطظعغفقکگلمنوهی])"
    ),
    (
        ProvisionType.SUBCLAUSE,
        r"(?:جزء|زیر\s*بند|زیربند)\s*([۰-۹0-9]+)"
    ),
    (
        ProvisionType.CLAUSE,
        r"(?:بند)\s*([۰-۹0-9]+)"
    ),
    (
        ProvisionType.NOTE,
        r"تبصره\s*([۰-۹0-9]+)?"
    ),
    (
        ProvisionType.ARTICLE,
        r"ماده\s*([۰-۹0-9]+|واحده)"
    ),
]


def parse_provision_reference(reference):
    """
    تمام reference ها را پیدا می‌کند.
    خروجی از آخرین reference به اولین reference مرتب شده است.
    """

    reference = norm(reference)

    if not reference:
        return []

    if reference.upper() == "ALL":
        return [("ALL", "ALL")]

    matches = []

    for provision_type, pattern in PROVISION_PATTERNS:
        for match in re.finditer(pattern, reference):
            matches.append(
                (
                    match.start(),
                    provision_type,
                    norm(match.group(1) or "")
                )
            )

    # آخرین reference در متن اولویت دارد
    matches.sort(
        key=lambda x: x[0],
        reverse=True
    )

    return [
        (provision_type, number)
        for _, provision_type, number in matches
    ]


def resolve_provision(document, reference):

    if not document or not reference:
        return None

    candidates = parse_provision_reference(reference)

    if not candidates:
        return None


    # ALL هیچ provision خاصی ندارد
    if candidates[0][0] == "ALL":
        return None


    provisions = list(
        LegalProvision.objects
        .filter(element__document=document)
        .select_related("element")
    )


    # از آخرین reference به عقب امتحان می‌کنیم
    for provision_type, number in candidates:

        for provision in provisions:

            if (
                provision.provision_type == provision_type
                and norm(provision.number) == norm(number)
            ):
                return provision


    return None



def get_value(item, *keys):

    for key in keys:
        value = item.get(key)

        if value not in (None, ""):
            return value

    return ""



def resolve_source_provision(item, source_document):

    reference = get_value(
        item,
        "source_provision",
        "source_article",
        "source_reference"
    )

    if reference:
        provision = resolve_provision(
            source_document,
            reference
        )

        if provision:
            return provision


    source_id = get_value(
        item,
        "source_provision_id",
        "source_id"
    )

    if source_id:

        try:
            return LegalProvision.objects.get(
                id=int(source_id),
                element__document=source_document
            )

        except (
            ValueError,
            LegalProvision.DoesNotExist
        ):
            pass


    return None



def resolve_target(item):

    document_title = get_value(
        item,
        "target_document",
        "target_law",
        "target_document_title"
    )


    provision_reference = get_value(
        item,
        "target_provision",
        "target_article",
        "target_reference"
    )


    target_document_id = get_value(
        item,
        "target_document_id"
    )


    if target_document_id:

        try:
            document = LegalDocument.objects.get(
                id=int(target_document_id)
            )

        except (
            ValueError,
            LegalDocument.DoesNotExist
        ):
            document = None

    else:
        document = resolve_document(document_title)



    if not document:
        return None, None



    target_provision_id = get_value(
        item,
        "target_provision_id"
    )


    if target_provision_id:

        try:

            provision = LegalProvision.objects.get(
                id=int(target_provision_id),
                element__document=document
            )

            return document, provision


        except (
            ValueError,
            LegalProvision.DoesNotExist
        ):
            pass



    return (
        document,
        resolve_provision(
            document,
            provision_reference
        )
    )



def resolve_relationship_type(item, default=None):

    value = get_value(
        item,
        "relation",
        "relationship",
        "relationship_type",
        "type"
    )


    if not value:
        return default


    value = norm(value).lower()


    aliases = {

        "amends": RelationshipType.AMENDS,
        "اصلاح": RelationshipType.AMENDS,

        "modifies": RelationshipType.MODIFIES,

        "repeals": RelationshipType.REPEALS,
        "نسخ": RelationshipType.REPEALS,

        "cancel": RelationshipType.CANCELS,
        "لغو": RelationshipType.CANCELS,

        "annuls": RelationshipType.ANNULS,
        "ابطال": RelationshipType.ANNULS,

        "suspends": RelationshipType.SUSPENDS,
        "تعلیق": RelationshipType.SUSPENDS,

        "revives": RelationshipType.REVIVES,
        "احیا": RelationshipType.REVIVES,

        "extends": RelationshipType.EXTENDS,
        "تمدید": RelationshipType.EXTENDS,

        "expires": RelationshipType.EXPIRES,
        "انقضا": RelationshipType.EXPIRES,

        "conflicts": RelationshipType.CONFLICTS,
        "تعارض": RelationshipType.CONFLICTS,

        "takhsis": RelationshipType.TAKHSIS,
        "تخصیص": RelationshipType.TAKHSIS,

        "taqyid": RelationshipType.TAQYID,
        "تقیید": RelationshipType.TAQYID,

        "takhassos": RelationshipType.TAKHASSOS,
        "تخصص": RelationshipType.TAKHASSOS,

        "hokumat": RelationshipType.HOKUMAT,
        "حکومت": RelationshipType.HOKUMAT,

        "references": RelationshipType.REFERENCES,
        "ارجاع": RelationshipType.REFERENCES,

        "elaborates": RelationshipType.ELABORATES,
        "تبیین": RelationshipType.ELABORATES,

        "implements": RelationshipType.IMPLEMENTS,
        "اجرا": RelationshipType.IMPLEMENTS,

        "identical": RelationshipType.IDENTICAL,

        "replaces": RelationshipType.REPLACES,
        "جایگزینی": RelationshipType.REPLACES,

        "adds": RelationshipType.ADDS,
        "الحاق": RelationshipType.ADDS,

        "removes": RelationshipType.REMOVES,
        "حذف": RelationshipType.REMOVES,
    }


    return aliases.get(value, default)



def create_relationship(
    source,
    target,
    relationship_type,
    item
):

    if not source or not target or not relationship_type:
        return None


    relationship, _ = LegalRelationship.objects.get_or_create(
        source=source,
        target=target,
        relationship_type=relationship_type
    )


    RelationshipContext.objects.create(

        relationship=relationship,

        source_text=norm(
            get_value(item, "source_text")
        ),

        target_text=norm(
            get_value(item, "target_text")
        ),

        old_text=norm(
            get_value(item, "old_text")
        ),

        new_text=norm(
            get_value(item, "new_text")
        ),

        source_date=norm(
            get_value(item, "source_date")
        ),

        target_date=norm(
            get_value(item, "target_date")
        ),

        effective_date=norm(
            get_value(item, "effective_date")
        ),

        reference_docs=item.get(
            "reference_docs"
        ) or [],

        reference_provisions=item.get(
            "reference_provisions"
        ) or [],

        evidence=norm(
            get_value(item, "evidence")
        ),
    )


    return relationship



def extract_relation_items(data):

    if isinstance(data, list):
        return data


    if not isinstance(data, dict):
        return []


    result = []


    for key in (
        "relations",
        "relationships"
    ):

        if isinstance(data.get(key), list):
            result.extend(data[key])


    for key, value in data.items():

        if key in {
            "relations",
            "relationships"
        }:
            continue


        if isinstance(value, list):

            if all(
                isinstance(x, dict)
                for x in value
            ):
                result.extend(value)


    return result



@transaction.atomic
def resolve_relationships(
    source_document,
    data,
    default_relationship_type=None
):

    items = extract_relation_items(data)

    created = []

    unresolved = []


    for item in items:

        relationship_type = resolve_relationship_type(
            item,
            default_relationship_type
        )


        source = resolve_source_provision(
            item,
            source_document
        )


        target_document, target = resolve_target(item)



        if (
            not source
            or not target
            or not relationship_type
        ):

            unresolved.append(
                {
                    "item": item,
                    "source": source.id if source else None,
                    "target_document": (
                        target_document.id
                        if target_document
                        else None
                    ),
                    "target": (
                        target.id
                        if target
                        else None
                    ),
                    "relationship_type": relationship_type,
                }
            )

            continue



        relationship = create_relationship(
            source,
            target,
            relationship_type,
            item
        )


        if relationship:
            created.append(
                relationship.id
            )


    return {
        "created": created,
        "unresolved": unresolved,
    }