import copy
import unittest
import uuid
from decimal import Decimal
from types import SimpleNamespace

from app.services import payment_matches_order


class PaymentMetadataTests(unittest.TestCase):
    def setUp(self):
        self.order = SimpleNamespace(
            id=uuid.uuid4(),
            customer_id=uuid.uuid4(),
            plan_id=uuid.uuid4(),
            amount=Decimal("299.00"),
        )
        self.payment = {
            "status": "succeeded",
            "amount": {"value": "299.00", "currency": "RUB"},
            "metadata": {
                "order_id": str(self.order.id),
                "customer_id": str(self.order.customer_id),
                "plan_id": str(self.order.plan_id),
            },
        }

    def test_accepts_exact_order_metadata(self):
        self.assertTrue(payment_matches_order(self.payment, self.order))

    def test_rejects_wrong_plan(self):
        payment = copy.deepcopy(self.payment)
        payment["metadata"]["plan_id"] = str(uuid.uuid4())
        self.assertFalse(payment_matches_order(payment, self.order))

    def test_rejects_wrong_customer(self):
        payment = copy.deepcopy(self.payment)
        payment["metadata"]["customer_id"] = str(uuid.uuid4())
        self.assertFalse(payment_matches_order(payment, self.order))

    def test_rejects_wrong_amount_currency_or_order(self):
        for path, value in (
            (("amount", "value"), "749.00"),
            (("amount", "currency"), "USD"),
            (("metadata", "order_id"), str(uuid.uuid4())),
        ):
            payment = copy.deepcopy(self.payment)
            payment[path[0]][path[1]] = value
            self.assertFalse(payment_matches_order(payment, self.order))


if __name__ == "__main__":
    unittest.main()
