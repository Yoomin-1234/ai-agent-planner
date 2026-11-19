import unittest

from app.services.replan_service import (
    _fallback_context,
    _merge_context,
    _filter_products,
    _parse_message_changes,
)


class ReplanServiceTests(unittest.TestCase):

    def test_fallback_context_preserves_search_context(self):
        plan = {
            "search_context": {
                "keyword": "니트",
                "brand": "브랜드A",
                "gender": "women",
                "limit": 10,
                "exclude_product_ids": ["100"],
            }
        }

        context = _fallback_context(plan)

        self.assertEqual(context["keyword"], "니트")
        self.assertEqual(context["brand"], "브랜드A")
        self.assertEqual(context["gender"], "women")
        self.assertEqual(context["exclude_product_ids"], ["100"])

    def test_merge_context_preserves_existing_conditions(self):
        plan = {
            "search_context": {
                "keyword": "니트",
                "brand": "브랜드A",
                "gender": "women",
                "max_price": 100000,
                "limit": 10,
            }
        }

        context, changes = _merge_context(
            plan,
            "화이트 색상으로 바꿔줘",
            {},
        )

        self.assertEqual(context["keyword"], "니트")
        self.assertEqual(context["brand"], "브랜드A")
        self.assertEqual(context["gender"], "women")
        self.assertEqual(context["color"], "화이트")

    def test_excluded_product_ids_are_accumulated(self):
        plan = {
            "search_context": {
                "keyword": "니트",
                "exclude_product_ids": ["100"],
            }
        }

        context, _ = _merge_context(
            plan,
            "상품 ID 200 제외해줘",
            {},
        )

        self.assertEqual(
            set(context["exclude_product_ids"]),
            {"100", "200"},
        )

    def test_filter_products_excludes_invalid_products(self):
        items = [
            {
                "product_id": 1,
                "name": "상품1",
                "sale_price": 50000,
                "gender": "여성",
            },
            {
                "product_id": 2,
                "name": "상품2",
                "sale_price": 50000,
                "gender": "여성",
            },
            {
                "product_id": 3,
                "name": "상품3",
                "sale_price": 200000,
                "gender": "여성",
            },
        ]

        context = {
            "exclude_product_ids": ["1"],
            "gender": "women",
            "min_price": None,
            "max_price": 100000,
        }

        result = _filter_products(items, context)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["product_id"], 2)

    def test_parse_message_changes(self):
        changes = _parse_message_changes(
            "여성용 화이트 니트 5만원 이하로 추천해줘"
        )

        self.assertEqual(changes["gender"], "women")
        self.assertEqual(changes["color"], "화이트")
        self.assertEqual(changes["max_price"], 50000)


if __name__ == "__main__":
    unittest.main()
