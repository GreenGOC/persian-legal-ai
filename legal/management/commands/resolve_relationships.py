import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError


def parse_output_file(path):
    """
    Extract and parse only output field.
    Ignores huge input fields.
    """

    with path.open(
        "r",
        encoding="utf-8"
    ) as f:

        for line in f:

            line = line.strip()

            if not line.startswith('"output"'):
                continue

            _, value = line.split(":", 1)

            value = value.strip().rstrip(",")

            try:
                # decode escaped JSON string
                output = json.loads(value)

            except json.JSONDecodeError:
                return None

            try:
                return json.loads(output)

            except json.JSONDecodeError:
                return None

    return None



def parse_relationship_filename(filename):

    stem = Path(filename).stem

    parts = stem.split("_")

    if "progress" in parts:
        return None

    if len(parts) < 2:
        return None

    relation = parts[-1]

    ids = []

    for part in parts[:-1]:

        if not part.isdigit():
            return None

        ids.append(int(part))


    return {
        "source_id": ids[0],
        "target_ids": ids[1:],
        "relation": relation,
    }



def extract_relation_items(data):

    if not isinstance(data, dict):
        return []

    result = []

    for key, value in data.items():

        if isinstance(value, list) and all(
            isinstance(x, dict)
            for x in value
        ):
            result.extend(value)

    return result



class Command(BaseCommand):

    help = "Parse relationship outputs"


    def add_arguments(self, parser):

        parser.add_argument(
            "--directory",
            default="data/relationships"
        )


    def handle(self, *args, **options):

        directory = Path(
            options["directory"]
        )


        if not directory.exists():

            raise CommandError(
                f"Missing directory: {directory}"
            )


        files = sorted(
            directory.glob("*.json")
        )


        processed = 0
        extracted = 0


        for file_path in files:


            metadata = parse_relationship_filename(
                file_path.name
            )


            if not metadata:

                self.stdout.write(
                    f"SKIP: {file_path.name}"
                )

                continue



            data = parse_output_file(
                file_path
            )


            if not data:

                self.stdout.write(
                    self.style.ERROR(
                        f"NO OUTPUT: {file_path.name}"
                    )
                )

                continue



            items = extract_relation_items(
                data
            )


            processed += 1


            self.stdout.write("")
            self.stdout.write("=" * 90)

            self.stdout.write(
                self.style.SUCCESS(
                    file_path.name
                )
            )

            self.stdout.write(
                f"relation={metadata['relation']}"
            )

            self.stdout.write(
                f"found={data.get('found')}"
            )

            self.stdout.write(
                f"count={len(items)}"
            )

            self.stdout.write("=" * 90)



            for i, item in enumerate(
                items,
                1
            ):

                extracted += 1

                self.stdout.write("")
                self.stdout.write(
                    f"RELATION #{i}"
                )

                self.stdout.write(
                    "-" * 70
                )


                for key in (
                    "kind",
                    "relation",
                    "source_document",
                    "source_provision",
                    "target_document",
                    "target_provision",
                    "evidence",
                ):

                    if key in item:

                        self.stdout.write(
                            f"{key}: {item[key]}"
                        )


                input(
                    "\nENTER..."
                )


        self.stdout.write("")
        self.stdout.write("=" * 90)
        self.stdout.write(
            f"Processed files: {processed}"
        )

        self.stdout.write(
            f"Extracted relationships: {extracted}"
        )

        self.stdout.write("=" * 90)