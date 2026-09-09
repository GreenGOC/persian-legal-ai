from pathlib import Path

from django.test import TestCase

from pymilvus import utility

from legal.models import (
    LegalDocument,
    LegalElement,
    LegalProvision,
)

from legal.services.retrieval.dense import (
    DenseIndexer,
    DenseRetriever,
    EmbeddingModel,
    resolve_local_model_path,
)


class DenseRetrievalTest(TestCase):
    COLLECTION_NAME = "test_legal_provisions"

    @classmethod
    def setUpTestData(cls):
        cls.document_civil = LegalDocument.objects.create(
            title="قانون مدنی",
        )

        cls.document_labor = LegalDocument.objects.create(
            title="قانون کار",
        )

        cls.document_commercial = LegalDocument.objects.create(
            title="قانون تجارت",
        )

        element_1 = LegalElement.objects.create(
            document=cls.document_civil,
            element_type="PROVISION",
            order=1,
        )

        cls.provision_contract = LegalProvision.objects.create(
            element=element_1,
            provision_type="ARTICLE",
            number="۱",
            title="قرارداد",
            text=(
                "قرارداد با توافق طرفین ایجاد می‌شود "
                "و طرفین نسبت به تعهدات قراردادی مسئول هستند."
            ),
        )

        element_2 = LegalElement.objects.create(
            document=cls.document_labor,
            element_type="PROVISION",
            order=1,
        )

        cls.provision_termination = LegalProvision.objects.create(
            element=element_2,
            provision_type="ARTICLE",
            number="۲",
            title="فسخ قرارداد",
            text=(
                "در صورت وجود شرایط قانونی، هر یک از طرفین "
                "می‌تواند قرارداد را فسخ نماید."
            ),
        )

        element_3 = LegalElement.objects.create(
            document=cls.document_commercial,
            element_type="PROVISION",
            order=1,
        )

        cls.provision_sale = LegalProvision.objects.create(
            element=element_3,
            provision_type="ARTICLE",
            number="۳",
            title="بیع",
            text=(
                "بیع عبارت است از تملیک عین به عوض معلوم "
                "و فروشنده مکلف به تسلیم مبیع است."
            ),
        )

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.embedding_model = EmbeddingModel()

        cls.indexer = DenseIndexer(
            embedding_model=cls.embedding_model,
        )

        cls.indexer.COLLECTION_NAME = cls.COLLECTION_NAME
        cls.indexer.connect()

        cls.collection = cls.indexer.create_collection()

        cls.indexer.index(
            [
                cls.provision_contract,
                cls.provision_termination,
                cls.provision_sale,
            ]
        )

        cls.collection.flush()
        cls.collection.load()

    @classmethod
    def tearDownClass(cls):
        if utility.has_collection(cls.COLLECTION_NAME):
            utility.drop_collection(cls.COLLECTION_NAME)

        super().tearDownClass()

    def _get_retriever(self):
        retriever = DenseRetriever(
            embedding_model=self.embedding_model,
        )

        retriever.COLLECTION_NAME = self.COLLECTION_NAME
        retriever.connect()

        return retriever

    def test_model_path_resolution_uses_valid_snapshot(self):
        model_root = Path(__file__).resolve().parents[3] / "Embedder model"
        resolved = resolve_local_model_path(str(model_root))

        self.assertTrue(Path(resolved).is_dir())
        self.assertTrue((Path(resolved) / "config.json").exists())
        self.assertNotEqual(str(Path(resolved).parent), str(model_root))

    def test_embedding_model_loads(self):
        self.assertIsNotNone(self.embedding_model.model)

    def test_embedding_dimension_is_valid(self):
        self.assertGreater(
            self.embedding_model.dimension,
            0,
        )

    def test_query_embedding_has_correct_dimension(self):
        vector = self.embedding_model.encode_query("شرایط فسخ قرارداد چیست؟")

        self.assertEqual(
            len(vector),
            self.embedding_model.dimension,
        )

    def test_collection_contains_indexed_provisions(self):
        self.assertEqual(
            self.collection.num_entities,
            3,
        )

    def test_dense_search_returns_results(self):
        retriever = self._get_retriever()

        results = retriever.search(
            "شرایط فسخ قرارداد چیست؟",
            top_k=3,
        )

        self.assertGreater(
            len(results),
            0,
        )

    def test_dense_search_returns_scores(self):
        retriever = self._get_retriever()

        results = retriever.search(
            "شرایط فسخ قرارداد چیست؟",
            top_k=3,
        )

        for result in results:
            self.assertIn("provision", result)
            self.assertIn("score", result)

            self.assertGreaterEqual(
                result["score"],
                -1.0,
            )

            self.assertLessEqual(
                result["score"],
                1.0,
            )

    def test_semantically_related_provision_is_ranked_first(self):
        retriever = self._get_retriever()

        results = retriever.search(
            "در چه شرایطی می‌توان قرارداد را فسخ کرد؟",
            top_k=3,
        )

        self.assertGreater(
            len(results),
            0,
        )

        self.assertEqual(
            results[0]["provision"],
            self.provision_termination,
        )

    def test_top_k_is_respected(self):
        retriever = self._get_retriever()

        results = retriever.search(
            "قرارداد",
            top_k=2,
        )

        self.assertLessEqual(
            len(results),
            2,
        )

    def test_retrieved_provision_exists_in_database(self):
        retriever = self._get_retriever()

        results = retriever.search(
            "فسخ قرارداد",
            top_k=3,
        )

        database_ids = set(
            LegalProvision.objects.values_list(
                "id",
                flat=True,
            )
        )

        for result in results:
            self.assertIn(
                result["provision"].id,
                database_ids,
            )
