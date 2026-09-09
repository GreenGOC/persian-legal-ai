from django.test import TestCase

from legal.models import (
    LegalDocument,
    LegalElement,
    LegalProvision,
)

from legal.services.retrieval.bm25 import BM25Retriever


class BM25RetrieverTest(TestCase):

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

    def test_search_returns_results(self):
        retriever = BM25Retriever()

        results = retriever.search(
            "فسخ قرارداد",
            top_k=3,
        )
        print(results)
        self.assertGreater(
            len(results),
            0,
        )

        self.assertEqual(
            results[0]["provision"],
            self.provision_termination,
        )

    def test_search_returns_scores(self):
        retriever = BM25Retriever()

        results = retriever.search(
            "فسخ قرارداد",
            top_k=3,
        )

        for result in results:
            self.assertIn(
                "provision",
                result,
            )

            self.assertIn(
                "score",
                result,
            )

            self.assertGreater(
                result["score"],
                0,
            )

    def test_top_k_is_respected(self):
        retriever = BM25Retriever()

        results = retriever.search(
            "قرارداد",
            top_k=1,
        )

        self.assertLessEqual(
            len(results),
            1,
        )

    def test_unrelated_query_returns_no_results(self):
        retriever = BM25Retriever()

        results = retriever.search(
            "ورشکستگی",
            top_k=5,
        )

        self.assertEqual(
            results,
            [],
        )

    def test_document_title_is_indexed(self):
        retriever = BM25Retriever()

        results = retriever.search(
            "کار",
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

    def test_search_can_find_provision_by_title(self):
        retriever = BM25Retriever()

        results = retriever.search(
            "بیع",
            top_k=3,
        )

        self.assertGreater(
            len(results),
            0,
        )

        self.assertEqual(
            results[0]["provision"],
            self.provision_sale,
        )

    def test_empty_query_returns_no_results(self):
        retriever = BM25Retriever()

        results = retriever.search(
            "",
            top_k=5,
        )

        self.assertEqual(
            results,
            [],
        )
