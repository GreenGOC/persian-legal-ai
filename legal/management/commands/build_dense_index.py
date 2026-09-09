from django.core.management.base import BaseCommand
from legal.services.retrieval.dense import DenseIndexer, EmbeddingModel


class Command(BaseCommand):
    help = "Build the dense retrieval index."

    def add_arguments(self, parser):
        parser.add_argument(
            "--device",
            default=None,
            help="Embedding device, e.g. cpu or cuda.",
        )

    def handle(self, *args, **options):
        device = options["device"]
        self.stdout.write("Initializing retrieval engine...")
        embedding_model = EmbeddingModel(device=device)
        dense_indexer = DenseIndexer(embedding_model=embedding_model)

        self.stdout.write("Building dense index...")
        dense_indexer.connect()
        total_indexed = dense_indexer.index_all()
        self.stdout.write(
            self.style.SUCCESS(f"Finished. Indexed {total_indexed} provisions.")
        )
