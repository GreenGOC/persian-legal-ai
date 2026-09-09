from pathlib import Path
import json
from django.core.management.base import BaseCommand
from hazm import Normalizer

PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"
ENGLISH_DIGITS = "0123456789"

DIGIT_TRANSLATION = str.maketrans(
    PERSIAN_DIGITS + ARABIC_DIGITS,
    ENGLISH_DIGITS + ENGLISH_DIGITS,
)
normalizer = Normalizer()

from ...services.importer.importer import read_file, import_document


class Command(BaseCommand):
    help = "Import legal documents from JSON files"

    def add_arguments(self, parser):
        parser.add_argument(
            "directory", type=str, help="Directory containing JSON files"
        )

    def handle(self, *args, **options):
        directory = Path(options["directory"])
        if not directory.exists():
            self.stderr.write(self.style.ERROR(f"Directory doesn't exist: {directory}"))
            return
        if not directory.is_dir():
            self.stderr.write(self.style.ERROR(f"Path is not a directory: {directory}"))
            return

        files = sorted(directory.glob("*.json"))
        if not files:
            self.stdout.write(self.style.WARNING(f"No JSON files found in {directory}"))
            return

        success_count = 0
        failure_count = 0
        skipped_count = 0
        erroneous = []
        all_titles: dict = {}
        for index, path in enumerate(files, start=1):
            self.stdout.write(f"[{index}/{len(files)}] {path.name}")
            try:
                data = read_file(path)
                title = normalizer.normalize(
                    data.get("title", "").translate(DIGIT_TRANSLATION)
                ).strip()

                if title in all_titles:
                    self.stdout.write(
                        self.style.WARNING(f"  Skipped {title}: It's repeated")
                    )
                    skipped_count += 1
                    all_titles[title] += 1
                    continue

                document = import_document(data)
                if document is None:
                    self.stdout.write(
                        self.style.WARNING(f"  Skipped {title}: It's not iranian")
                    )
                    skipped_count += 1
                    continue
                all_titles[title] = 1
                success_count += 1
                self.stdout.write(self.style.SUCCESS(f"  Imported: {document.title}"))
            except Exception as exc:
                failure_count += 1
                self.stderr.write(self.style.ERROR(f" FAILED:  {path.name}"))
                self.stderr.write(f"    {type(exc).__name__}: {exc}")
                erroneous.append((path.name, exc))
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"Successfully imported: {success_count}"))
        if skipped_count:
            self.stdout.write(self.style.WARNING(f"Skipped: {skipped_count}"))
        if failure_count:
            self.stderr.write(self.style.ERROR(f"Failed: {failure_count}"))
            for error in erroneous:
                print(f"Error File: {error[0]}, Reason: {error[1]}")
        print("Duplicated: ")
        dup_dict = {(rec, val) for rec, val in all_titles.items() if val >= 2}
        for record, value in dup_dict:
            print(f"Title: {record}, Rep: {value}")
