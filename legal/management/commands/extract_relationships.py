from pathlib import Path
import os

from django.core.management.base import BaseCommand, CommandError
from dotenv import load_dotenv

from ...models import LegalDocument
from ...services.llm.client import LLMClient
from ...services.relationships.extractor import LegalRelationshipExtractor, GROUP_CONFIG

load_dotenv()


class Command(BaseCommand):
    help = "Extract legal relationships between selected legal documents."

    def add_arguments(self, parser):
        parser.add_argument(
            "--documents",
            nargs="*",
            type=int,
            help="LegalDocument IDs. If omitted, all documents are used.",
        )
        parser.add_argument(
            "--relationship",
            type=str,
            help="Relationship group to extract. Use ALL for all compatible groups.",
        )
        parser.add_argument(
            "--output",
            type=str,
            default="data/relationships",
            help="Output directory for JSON files.",
        )

    def handle(self, *args, **options):
        document_ids = options.get("documents")
        relationship = options.get("relationship")
        output_dir = options["output"]
        if not relationship:
            relationship = self.ask_relationship()

        relationship = relationship.upper()
        if relationship != "ALL" and relationship not in GROUP_CONFIG:
            raise CommandError(f"Unknown relationship type: {relationship}")

        if document_ids:
            documents = []
            for document_id in document_ids:
                document = LegalDocument.objects.filter(id=document_id).first()
                if not document:
                    raise CommandError(f"LegalDocument not found: {document_id}")
                documents.append(document)
            found_ids = {document.id for document in documents}
            missing_ids = [document_id for document_id in document_ids if document_id not in found_ids]
            if missing_ids:
                raise CommandError(f"LegalDocument not found: {', '.join(map(str, missing_ids))}")
            documents.sort(key=lambda document: document_ids.index(document.id))
        else:
            documents = list(LegalDocument.objects.all().order_by("id"))
        if not documents:
            raise CommandError("No LegalDocument found.")

        llm = LLMClient(base_url=os.getenv("OPEN_ROUTER_API_ENDPOINT"), api_key=os.getenv("OPEN_ROUTER_API_KEY"), model=os.getenv("OPEN_ROUTER_MODEL"))
        extractor = LegalRelationshipExtractor(llm_client=llm)
        relationships = list(GROUP_CONFIG) if relationship == "ALL" else [relationship]

        for group_name in relationships:
            required_documents = GROUP_CONFIG[group_name]["documents"]
            if required_documents != len(documents):
                self.stdout.write(self.style.WARNING(f"Skipping {group_name}: requires {required_documents} documents, but {len(documents)} were provided." ))
                continue

            self.stdout.write(f"Extracting {group_name} between {len(documents)} documents...")
            path = extractor.extract_documents_to_json(group_name=group_name, documents=documents, output_dir=Path(output_dir))
            self.stdout.write(self.style.SUCCESS(f"Saved: {path}"))

    def ask_relationship(self):
        available = ", ".join(GROUP_CONFIG.keys())
        self.stdout.write(f"Available relationship groups:\n{available}")
        relationship = input("\nEnter relationship type (or ALL): ").strip()

        if not relationship:
            raise CommandError("Relationship type is required. Use ALL for all relationships.")
        return relationship