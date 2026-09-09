from django.db import models


class Source(models.TextChoices):
    NEZAMAT = "nezamat", "Nezamat"
    RRK = "rrk", "RRK"
    QAVANIN = "qavanin", "Qavanin"
    OTHER = "other", "Other"


class DocumentType(models.TextChoices):
    LAW = "law", "Law"
    REGULATION = "regulation", "Regulation"
    BYLAW = "bylaw", "Bylaw"
    CIRCULAR = "circular", "Circular"
    DECREE = "decree", "Decree"
    RESOLUTION = "resolution", "Resolution"
    EXECUTIVE_RESOLUTION = "executive_resolution", "Executive Resolution"
    OTHER = "other", "Other"


class DocumentStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    REPEALED = "repealed", "Repealed"
    AMENDED = "amended", "Amended"
    UNKNOWN = "unknown", "Unknown"


class ProcessingStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    PROCESSING = "processing", "Processing"
    PROCESSED = "processed", "Processed"
    FAILED = "failed", "Failed"
    REJECTED = "rejected", "Rejected"


class ElementType(models.TextChoices):
    STRUCTURAL = "structural", "Structural"
    PROVISION = "provision", "Provision"


class StructuralType(models.TextChoices):
    BOOK = "book", "Book"
    PART = "part", "Part"
    CHAPTER = "chapter", "Chapter"
    SECTION = "section", "Section"
    SUBSECTION = "subsection", "Subsection"
    INTRODUCTION = "introduction", "Introduction"
    OTHER = "other", "Other"


class ProvisionType(models.TextChoices):
    CONSTITUTIONAL_PRINCIPLE = "constitutional_principle", "Constitutional Principle"
    ARTICLE = "article", "Article"
    NOTE = "note", "Note"
    CLAUSE = "clause", "Clause"
    SUBCLAUSE = "subclause", "Subclause"
    ITEM = "item", "Item"
    OTHER = "other", "Other"


class RelationshipType(models.TextChoices):
    AMENDS = "amends", "Amends"
    MODIFIES = "modifies", "Modifies"
    REPEALS = "repeals", "Repeals"
    REPLACES = "replaces", "Replaces"
    REFERENCES = "references", "References"
    ADDS = "adds", "Adds"
    CONFLICTS = "conflicts", "Conflicts"
    IDENTICAL = "identical", "Identical"
    RELATED = "related", "Related"


class VersionStatus(models.TextChoices):
    CURRENT = "current", "Current"
    SUPERSEDED = "superseded", "Superseded"
    INVALID = "invalid", "Invalid"


class HierarchyLevel(models.TextChoices):
    CONSTITUTION = "constitution", "Constitution"
    ORDINARY_LAW = "ordinary_law", "OrdinaryLaw"
    EXECUTIVE_REGULATION = "executive_regulation", "ExecutiveRegulation"
    CIRCULAR = "circular", "Circular"


class LegalEntity(models.Model):
    canonical_title = models.TextField()
    entity_type = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.canonical_title


class SourceDocument(models.Model):
    source = models.CharField(
        max_length=50, choices=Source.choices, default=Source.NEZAMAT, db_index=True
    )
    source_id = models.CharField(max_length=255, blank=True, null=True)
    url = models.URLField(max_length=2000)
    title = models.TextField()
    json_path = models.TextField(blank=True)
    processing_status = models.CharField(
        max_length=30,
        choices=ProcessingStatus.choices,
        default=ProcessingStatus.PENDING,
        db_index=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["source", "source_id"],
                name="unique_source_document_id",
            ),
        ]

        indexes = [
            models.Index(fields=["source", "source_id"]),
            models.Index(fields=["processing_status"]),
        ]

    def __str__(self):
        return self.title


class LegalDocument(models.Model):
    document_id = models.CharField(max_length=500, blank=True, null=True)
    entity = models.ForeignKey(
        LegalEntity,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="documents",
    )
    title = models.TextField()
    hierarchy_level = models.CharField(
        max_length=32, choices=HierarchyLevel.choices, null=True, blank=True
    )
    document_type = models.CharField(
        max_length=50, choices=DocumentType.choices, blank=True
    )
    issuing_authority = models.CharField(max_length=500, blank=True)
    approval_date = models.CharField(max_length=20, blank=True)
    publication_date = models.CharField(max_length=20, blank=True)
    effective_date = models.CharField(max_length=20, blank=True)
    subject = models.TextField(blank=True)
    status = models.CharField(
        max_length=50,
        choices=DocumentStatus.choices,
        default=DocumentStatus.UNKNOWN,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            (models.Index(fields=["document_type", "status"])),
        ]

    def __str__(self):
        return self.title


class DocumentSource(models.Model):
    """
    Connects one canonical LegalDocument to one or more
    source-specific SourceDocuments.
    """

    document = models.ForeignKey(
        LegalDocument, on_delete=models.CASCADE, related_name="sources"
    )
    source_document = models.ForeignKey(
        SourceDocument, on_delete=models.CASCADE, related_name="legal_documents"
    )
    is_primary = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["document", "source_document"],
                name="unique_document_source",
            ),
        ]

        indexes = [
            models.Index(fields=["document", "is_primary"]),
        ]


class LegalElement(models.Model):
    document = models.ForeignKey(
        LegalDocument, on_delete=models.CASCADE, related_name="elements"
    )
    parent = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True, related_name="children"
    )
    element_type = models.CharField(max_length=30, choices=ElementType.choices)
    order = models.PositiveIntegerField()

    class Meta:
        ordering = ["order"]
        constraints = [
            models.UniqueConstraint(
                fields=["document", "parent", "order"],
                name="unique_element_order_per_parent",
            ),
        ]
        indexes = [
            models.Index(fields=["document", "parent", "order"]),
            models.Index(fields=["document", "element_type"]),
        ]


class StructuralElement(models.Model):
    element = models.OneToOneField(
        LegalElement, on_delete=models.CASCADE, related_name="structural"
    )
    structural_type = models.CharField(max_length=30, choices=StructuralType.choices)
    title = models.TextField(blank=True)
    number = models.CharField(max_length=50, blank=True)

    def __str__(self):
        return self.title or self.number or self.structural_type


class LegalProvision(models.Model):
    element = models.OneToOneField(
        LegalElement, on_delete=models.CASCADE, related_name="provision"
    )
    provision_type = models.CharField(max_length=30, choices=ProvisionType.choices)
    number = models.CharField(max_length=50, blank=True)
    title = models.TextField(blank=True)
    text = models.TextField()

    class Meta:
        indexes = [
            models.Index(fields=["provision_type"]),
        ]

    def __str__(self):
        return f"{self.provision_type} " f"{self.number}".strip()


class LegalVersion(models.Model):
    provision = models.ForeignKey(
        LegalProvision, on_delete=models.CASCADE, related_name="versions"
    )
    text = models.TextField()
    version_date = models.CharField(max_length=20, blank=True)
    status = models.CharField(max_length=50, choices=VersionStatus.choices, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["provision", "status"]),
        ]


class LegalRelationship(models.Model):
    source = models.ForeignKey(
        LegalProvision, on_delete=models.CASCADE, related_name="outgoing_relationships"
    )
    target = models.ForeignKey(
        LegalProvision, on_delete=models.CASCADE, related_name="incoming_relationships"
    )
    relationship_type = models.CharField(
        max_length=50, choices=RelationshipType.choices
    )
    confidence = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["source", "target", "relationship_type"],
                name="unique_legal_relationship",
            ),
        ]
        indexes = [
            models.Index(fields=["source", "relationship_type"]),
            models.Index(fields=["target", "relationship_type"]),
        ]


class RelationshipContext(models.Model):
    relationship = models.ForeignKey(
        LegalRelationship, on_delete=models.CASCADE, related_name="contexts"
    )
    source_text = models.TextField(blank=True)
    target_text = models.TextField(blank=True)
    old_text = models.TextField(blank=True)
    new_text = models.TextField(blank=True)
    source_date = models.CharField(max_length=20, blank=True)
    target_date = models.CharField(max_length=20, blank=True)
    effective_date = models.CharField(max_length=20, blank=True)
    reference_docs = models.JSONField(default=list, blank=True)
    reference_provisions = models.JSONField(default=list, blank=True)
    evidence = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
