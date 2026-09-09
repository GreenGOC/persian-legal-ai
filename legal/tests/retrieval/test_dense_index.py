from django.test import TestCase

from legal.models import LegalProvision
from legal.services.retrieval.dense import (
    DenseIndexer,
    EmbeddingModel,
)


class DenseIndexerTest(TestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.embedding_model = EmbeddingModel()
        cls.indexer = DenseIndexer(cls.embedding_model)

        cls.indexer.connect()
        cls.indexer.create_collection()

    def test_index_provisions(self):
        provisions = LegalProvision.objects.select_related(
            "element__document"
        ).order_by("id")[:10]

        count = self.indexer.index(provisions)

        self.assertEqual(
            count,
            10,
        )

        print(f"\nIndexed: {count}")
