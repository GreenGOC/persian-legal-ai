import json
import queue
import threading
from pathlib import Path

from django.core.management.base import BaseCommand

from legal.models import LegalProvision
from legal.services.llm.client import LLMClient
from legal.services.references.extractor import ReferenceExtractor
from legal.services.actions.extractor import ActionExtractor


class Command(BaseCommand):
    help = "Extract references and actions from LegalProvision objects."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            default="provision_results",
            help="Directory where JSON files will be saved.",
        )
        parser.add_argument(
            "--start-id",
            type=int,
            default=1000000,
            help="Start processing from this provision ID.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Maximum number of provisions to process.",
        )
        parser.add_argument(
            "--overwrite",
            action="store_true",
            help="Overwrite existing JSON files.",
        )

    def handle(self, **options):
        output_dir = Path(options["output"])
        output_dir.mkdir(parents=True, exist_ok=True)
        provisions = LegalProvision.objects.all().order_by("-id")

        if options["start_id"] is not None:
            provisions = provisions.filter(id__lte=options["start_id"])

        if options["limit"] is not None:
            provisions = provisions[: options["limit"]]

        total = provisions.count()
        self.stdout.write(f"Found {total} provisions.")

        reference_client = LLMClient(base_url="http://127.0.0.1:8082")
        reference_extractor = ReferenceExtractor(reference_client)

        action_client = LLMClient(base_url="http://127.0.0.1:8081")
        action_extractor = ActionExtractor(action_client)

        action_queue = queue.Queue()

        processed = 0
        skipped = 0
        failed = 0
        reference_failures = []
        action_failures = []

        def action_worker():
            while True:
                output_file = action_queue.get()
                if output_file is None:
                    action_queue.task_done()
                    break
                try:
                    self.process_actions(output_file, action_extractor)

                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f"[ACTION ERROR] {output_file.name}: {e}")
                    )
                    action_failures.append(output_file.name)

                finally:
                    action_queue.task_done()

        action_thread = threading.Thread(target=action_worker, daemon=True)
        action_thread.start()
        try:
            for provision in provisions.iterator():
                output_file = output_dir / f"{provision.id}.json"
                if output_file.exists() and not options["overwrite"]:
                    skipped += 1
                    self.stdout.write(f"[SKIP] {provision.id} - file already exists")
                    continue
                text = provision.text.strip()
                if not text:
                    skipped += 1
                    self.stdout.write(f"[SKIP] {provision.id} - empty text")
                    continue
                lines = [line.strip() for line in text.splitlines() if line.strip()]
                all_references = []
                try:
                    for line in lines:
                        references = reference_extractor.extract_from_text(line)
                        all_references.extend(references)
                    if not all_references:
                        self.stdout.write(f"[NO REF] {provision.id}")
                        continue
                    result = {
                        "provision_id": provision.id,
                        "text": text,
                        "references": all_references,
                        "actions": [],
                    }

                    with output_file.open("w", encoding="utf-8") as file:
                        json.dump(result, file, ensure_ascii=False, indent=2)

                    processed += 1
                    self.stdout.write(self.style.SUCCESS(f"[REFERENCE OK] {provision.id}"))

                    action_queue.put(output_file)

                except Exception as e:
                    failed += 1
                    self.stdout.write(self.style.ERROR(f"[REFERENCE ERROR] {provision.id}: {e}"))
                    reference_failures.append(provision.id)

        finally:
            action_queue.join()
            action_queue.put(None)
            action_thread.join()

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"Finished: "
                f"processed={processed}, "
                f"skipped={skipped}, "
                f"failed={failed}"
            )
        )
        with open("failures.txt", "w", encoding="utf-8") as f:
            f.write("-".join(reference_failures))
            f.write("====")
            f.write("-".join(action_failures))

    def process_actions(self, output_file, action_extractor):
        with output_file.open("r", encoding="utf-8") as file:
            result = json.load(file)
        references = result.get("references", [])
        actions = []
        for reference in references:
            source_line = reference.get("source_line", "")
            reference_raw_text = reference.get("raw_text", "")
            if not source_line or not reference_raw_text:
                actions.append({})
                continue
            action = action_extractor.extract_action(source_line=source_line, reference_raw_text=reference_raw_text)
            if action is None:
                actions.append({})
            else:
                actions.append({"type": action})

        result["actions"] = actions

        with output_file.open("w", encoding="utf-8") as file:
            json.dump(result, file, ensure_ascii=False, indent=2)
        self.stdout.write(self.style.SUCCESS(f"[ACTION OK] {output_file.stem}"))
