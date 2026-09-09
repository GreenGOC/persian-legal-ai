from django.test import SimpleTestCase

from legal.services.retrieval.bm25 import BM25


class BM25Test(SimpleTestCase):

    def setUp(self):
        self.corpus = [
            [
                "قانون",
                "مدنی",
                "ماده",
                "یک",
                "قرارداد",
                "عقد",
                "تعهد",
                "طرفین",
                "موضوع",
                "معامله",
                "رضایت",
                "اهلیت",
                "قصد",
                "اختیار",
            ],
            [
                "قانون",
                "مدنی",
                "قرارداد",
                "بیع",
                "فروشنده",
                "خریدار",
                "مبیع",
                "ثمن",
                "مال",
                "معامله",
                "تسلیم",
                "مالکیت",
                "انتقال",
                "تعهد",
                "طرفین",
            ],
            [
                "قانون",
                "مدنی",
                "فسخ",
                "قرارداد",
                "خیار",
                "فسخ",
                "عقد",
                "طرفین",
                "تعهد",
                "نقض",
                "قرارداد",
                "شرایط",
                "حقوق",
                "اختیار",
                "معامله",
            ],
            [
                "قانون",
                "مدنی",
                "اقاله",
                "قرارداد",
                "عقد",
                "طرفین",
                "تراضی",
                "فسخ",
                "تعهد",
                "حقوق",
                "معامله",
                "توافق",
                "رضایت",
                "طرفین",
            ],
            [
                "قانون",
                "کار",
                "کارگر",
                "کارفرما",
                "قرارداد",
                "کار",
                "حقوق",
                "دستمزد",
                "مزد",
                "مرخصی",
                "استخدام",
                "کارگاه",
                "تعهدات",
                "کارگر",
                "کارفرما",
            ],
            [
                "قانون",
                "کار",
                "اخراج",
                "کارگر",
                "فسخ",
                "قرارداد",
                "کار",
                "کارفرما",
                "ماده",
                "شرایط",
                "تخلف",
                "انضباطی",
                "حقوق",
                "مزایا",
                "پایان",
                "کار",
            ],
            [
                "قانون",
                "کار",
                "مرخصی",
                "کارگر",
                "استحقاق",
                "مرخصی",
                "سالانه",
                "حقوق",
                "دستمزد",
                "کارفرما",
                "کارگاه",
                "تعطیلات",
                "غیبت",
                "استخدام",
            ],
            [
                "قانون",
                "تجارت",
                "شرکت",
                "سهامی",
                "مجمع",
                "عمومی",
                "سهامدار",
                "هیئت",
                "مدیره",
                "سرمایه",
                "سهام",
                "شرکت",
                "تجاری",
                "مدیرعامل",
                "تصمیم",
            ],
            [
                "قانون",
                "تجارت",
                "ورشکستگی",
                "تاجر",
                "دیون",
                "طلبکار",
                "بدهکار",
                "دادگاه",
                "توقف",
                "پرداخت",
                "اموال",
                "تجاری",
                "ورشکسته",
                "مدیر",
                "تصفیه",
            ],
            [
                "قانون",
                "تجارت",
                "چک",
                "سفته",
                "اسناد",
                "تجاری",
                "دارنده",
                "صادرکننده",
                "پرداخت",
                "وجه",
                "سررسید",
                "تعهد",
                "بانک",
                "ظهرنویسی",
                "مسئولیت",
            ],
            [
                "قانون",
                "مجازات",
                "اسلامی",
                "جرم",
                "مجازات",
                "کیفر",
                "متهم",
                "دادگاه",
                "قاضی",
                "شاکی",
                "بزه",
                "مسئولیت",
                "کیفری",
                "قصد",
                "عمل",
            ],
            [
                "قانون",
                "مجازات",
                "اسلامی",
                "سرقت",
                "مال",
                "غیر",
                "جرم",
                "مجازات",
                "سارق",
                "مالک",
                "اموال",
                "شاکی",
                "دادگاه",
                "کیفر",
                "تعزیر",
            ],
            [
                "قانون",
                "مجازات",
                "اسلامی",
                "کلاهبرداری",
                "مال",
                "وجه",
                "فریب",
                "جرم",
                "مجازات",
                "متهم",
                "شاکی",
                "دادگاه",
                "ضرر",
                "زیان",
                "مالی",
            ],
            [
                "قانون",
                "مالیات",
                "مؤدی",
                "مالیات",
                "درآمد",
                "اظهارنامه",
                "مالیاتی",
                "اداره",
                "مالیات",
                "پرداخت",
                "جریمه",
                "مالیات",
                "تشخیص",
                "درآمد",
                "مشمول",
            ],
            [
                "قانون",
                "ثبت",
                "اسناد",
                "املاک",
                "مالک",
                "ملک",
                "ثبت",
                "سند",
                "رسمی",
                "دفترخانه",
                "انتقال",
                "مالکیت",
                "معامله",
                "ثبتی",
                "اداره",
            ],
        ]

        self.bm25 = BM25(self.corpus)

    def test_document_count(self):
        self.assertEqual(
            self.bm25.document_count,
            15,
        )

    def test_average_document_length(self):
        expected = sum(len(document) for document in self.corpus) / len(self.corpus)

        self.assertEqual(
            self.bm25.average_document_length,
            expected,
        )

    def test_document_frequencies(self):
        self.assertEqual(
            self.bm25.document_frequencies["قانون"],
            15,
        )

        self.assertEqual(
            self.bm25.document_frequencies["قرارداد"],
            6,
        )

        self.assertEqual(
            self.bm25.document_frequencies["ورشکستگی"],
            1,
        )

    def test_common_term_has_lower_idf(self):
        common_idf = self.bm25._idf("قانون")
        rare_idf = self.bm25._idf("ورشکستگی")

        self.assertLess(
            common_idf,
            rare_idf,
        )

    def test_unknown_term_has_zero_idf(self):
        self.assertEqual(
            self.bm25._idf("دانشگاه"),
            0.0,
        )

    def test_unrelated_document_has_zero_score(self):
        score = self.bm25.score(
            ["ورشکستگی"],
            0,
        )

        self.assertEqual(
            score,
            0.0,
        )

    def test_matching_document_has_positive_score(self):
        score = self.bm25.score(
            ["ورشکستگی"],
            8,
        )

        self.assertGreater(
            score,
            0,
        )

    def test_rare_term_has_strong_effect(self):
        bankruptcy_score = self.bm25.score(
            ["ورشکستگی"],
            8,
        )

        common_score = self.bm25.score(
            ["قانون"],
            8,
        )

        self.assertGreater(
            bankruptcy_score,
            common_score,
        )

    def test_contract_termination_query(self):
        results = self.bm25.get_top_n(
            ["فسخ", "قرارداد"],
            n=5,
        )

        top_documents = [index for index, score in results]

        self.assertIn(
            2,
            top_documents[:2],
        )

    def test_employment_query(self):
        results = self.bm25.get_top_n(
            ["کارگر", "کارفرما", "دستمزد"],
            n=5,
        )

        top_documents = [index for index, score in results]

        self.assertIn(
            4,
            top_documents[:2],
        )

    def test_company_query(self):
        results = self.bm25.get_top_n(
            ["شرکت", "سهامی", "سهامدار"],
            n=5,
        )

        top_documents = [index for index, score in results]

        self.assertEqual(
            top_documents[0],
            7,
        )

    def test_bankruptcy_query(self):
        results = self.bm25.get_top_n(
            ["ورشکستگی", "تاجر", "طلبکار"],
            n=5,
        )

        top_documents = [index for index, score in results]

        self.assertEqual(
            top_documents[0],
            8,
        )

    def test_tax_query(self):
        results = self.bm25.get_top_n(
            ["مالیات", "اظهارنامه", "درآمد"],
            n=5,
        )

        top_documents = [index for index, score in results]

        self.assertEqual(
            top_documents[0],
            13,
        )

    def test_registration_query(self):
        results = self.bm25.get_top_n(
            ["ثبت", "سند", "ملک", "دفترخانه"],
            n=5,
        )

        top_documents = [index for index, score in results]

        self.assertEqual(
            top_documents[0],
            14,
        )

    def test_get_scores_returns_all_documents(self):
        scores = self.bm25.get_scores(
            ["قرارداد", "فسخ"],
        )

        self.assertEqual(
            len(scores),
            len(self.corpus),
        )

    def test_top_n_limits_results(self):
        results = self.bm25.get_top_n(
            ["قانون"],
            n=3,
        )

        self.assertEqual(
            len(results),
            3,
        )

    def test_results_are_sorted_by_score(self):
        results = self.bm25.get_top_n(
            ["قرارداد", "فسخ"],
            n=10,
        )

        scores = [score for index, score in results]

        self.assertEqual(
            scores,
            sorted(scores, reverse=True),
        )
