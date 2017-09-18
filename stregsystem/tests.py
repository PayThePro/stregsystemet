# -*- coding: utf8 -*-
import datetime
from django.utils import timezone

from django.test import TestCase
from django.urls import reverse
from collections import Counter

from stregsystem import admin
from stregsystem.admin import ProductAdmin
from stregsystem.models import (
    GetTransaction,
    Member,
    PayTransaction,
    StregForbudError,
    Product,
    Sale,
    Room,
    Order,
    OrderItem,
    Payment,
    NoMoreInventoryError,
)
from stregsystem.models import (
    price_display,
    active_str
)
import stregsystem.parser as parser

try:
    from unittest.mock import patch
except ImportError:
    from mock import patch


def assertCountEqual(case, *args, **kwargs):
    try:
        case.assertCountEqual(*args, **kwargs)
    except AttributeError:
        case.assertItemsEqual(*args, **kwargs)


class ModelMiscTests(TestCase):
    def test_price_display_none(self):
        v = price_display(None)
        self.assertEqual(v, "0.00 kr.")

    def test_price_display_zero(self):
        v = price_display(0)
        self.assertEqual(v, "0.00 kr.")

    def test_price_display_one(self):
        v = price_display(1)
        self.assertEqual(v, "0.01 kr.")

    def test_price_display_hundred(self):
        v = price_display(100)
        self.assertEqual(v, "1.00 kr.")

    def test_active_str_true(self):
        v = active_str(True)
        self.assertEqual(v, "+")

    def test_active_str_false(self):
        v = active_str(False)
        self.assertEqual(v, "-")


class SaleViewTests(TestCase):
    fixtures = ["initial_data"]

    def test_make_sale_letter_quickbuy(self):
        response = self.client.post(
            reverse('quickbuy', args="1"),
            {"quickbuy": "jokke a"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed("stregsystem/error_invalidquickbuy.html")

    @patch('stregsystem.models.Member.can_fulfill')
    @patch('stregsystem.models.Member.fulfill')
    def test_make_sale_quickbuy_success(self, fulfill, can_fulfill):
        can_fulfill.return_value = True

        response = self.client.post(
            reverse('quickbuy', args=(1,)),
            {"quickbuy": "jokke 1"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "stregsystem/index_sale.html")

        assertCountEqual(self, response.context["products"], {
            Product.objects.get(id=1)
        })
        self.assertEqual(response.context["member"],
                         Member.objects.get(username="jokke"))

        fulfill.assert_called_once_with(PayTransaction(900))

    def test_make_sale_quickbuy_fail(self):
        member_username = 'jan'
        member_before = Member.objects.get(username=member_username)
        response = self.client.post(
            reverse('quickbuy', args=(1,)),
            {"quickbuy": member_username + " 1"}
        )
        member_after = Member.objects.get(username=member_username)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "stregsystem/error_stregforbud.html")
        self.assertEqual(member_before.balance, member_after.balance)

        self.assertEqual(response.context["member"],
                         Member.objects.get(username=member_username))

    def test_make_sale_quickbuy_wrong_product(self):
        response = self.client.post(
            reverse('quickbuy', args=(1,)),
            {"quickbuy": "jokke 99"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "stregsystem/menu.html")
        self.assertEqual(response.context["member"],
                         Member.objects.get(username="jokke"))

    @patch('stregsystem.models.Member.can_fulfill')
    @patch('stregsystem.models.Member.fulfill')
    def test_make_sale_menusale_fail(self, fulfill, can_fulfill):
        can_fulfill.return_value = False

        response = self.client.get(reverse('menu_sale', args=(1, 1, 1)))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "stregsystem/error_stregforbud.html")

        self.assertEqual(response.context["member"], Member.objects.get(id=1))

        fulfill.assert_not_called()

    @patch('stregsystem.models.Member.can_fulfill')
    @patch('stregsystem.models.Member.fulfill')
    def test_make_sale_menusale_success(self, fulfill, can_fulfill):
        can_fulfill.return_value = True

        response = self.client.get(reverse('menu_sale', args=(1, 1, 1)))
        self.assertTemplateUsed(response, "stregsystem/menu.html")

        self.assertEqual(response.status_code, 200)

        self.assertEqual(response.context["bought"], Product.objects.get(id=1))
        self.assertEqual(response.context["member"], Member.objects.get(id=1))

        fulfill.assert_called_once_with(PayTransaction(900))

    def test_quicksale_has_status_line(self):
        response = self.client.post(
            reverse('quickbuy', args=(1,)),
            {"quickbuy": "jokke 1"}
        )

        self.assertContains(
            response,
            "<b>jokke har lige købt Limfjordsporter for tilsammen "
            "9.00 kr.</b>",
            html=True
        )

    def test_usermenu(self):
        response = self.client.post(
            reverse('quickbuy', args=(1,)),
            {"quickbuy": "jokke"}
        )

        self.assertTemplateUsed(response, "stregsystem/menu.html")

    def test_quickbuy_empty(self):
        response = self.client.post(
            reverse('quickbuy', args=(1,)),
            {"quickbuy": ""}
        )

        self.assertTemplateUsed(response, "stregsystem/index.html")

    def test_index(self):
        response = self.client.post(
            reverse('index')
        )

        # Assert permanent redirect
        self.assertEqual(response.status_code, 301)

    def test_menu_index(self):
        response = self.client.post(
            reverse('menu_index', args=(1, ))
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "stregsystem/index.html")
        # Assert that the index screen at least contains one of the products in
        # the database. Technically this doesn't check everything exhaustively,
        # but it's better than nothing -Jesper 18/09-2017
        self.assertContains(response, "<td>Limfjordsporter</td>", html=True)

    def test_quickbuy_no_known_member(self):
        response = self.client.post(
            reverse('quickbuy', args=(1,)),
            {"quickbuy": "notinthere"}
        )

        self.assertTemplateUsed(
            response,
            "stregsystem/error_usernotfound.html"
        )

    def test_quicksale_increases_bought(self):
        before = Product.objects.get(id=2)
        before_member = Member.objects.get(username="jokke")

        response = self.client.post(
            reverse('quickbuy', args=(1,)),
            {"quickbuy": "jokke 2"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "stregsystem/index_sale.html")

        after = Product.objects.get(id=2)
        after_member = Member.objects.get(username="jokke")

        self.assertEqual(before.bought + 1, after.bought)
        # 900 is the product price
        self.assertEqual(before_member.balance - 900, after_member.balance)

    def test_quicksale_quanitity_none_noincrease(self):
        before = Product.objects.get(id=1)
        before_member = Member.objects.get(username="jokke")

        response = self.client.post(
            reverse('quickbuy', args=(1,)),
            {"quickbuy": "jokke 1"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "stregsystem/index_sale.html")

        after = Product.objects.get(id=1)
        after_member = Member.objects.get(username="jokke")

        self.assertEqual(before.bought, after.bought)
        # 900 is the product price
        self.assertEqual(before_member.balance - 900, after_member.balance)

    def test_quicksale_out_of_stock(self):
        before = Product.objects.get(id=1)
        before_member = Member.objects.get(username="jokke")

        response = self.client.post(
            reverse('quickbuy', args=(1,)),
            {"quickbuy": "jokke 3"}
        )

        self.assertEqual(response.status_code, 200)
        # I don't know which template to use (I should probably make one). So
        # for now let's just make sure that we at least don't use the one that
        # says "correct" - Jesper 14/09-2017
        self.assertTemplateNotUsed(response, "stregsystem/index_sale.html")

        after = Product.objects.get(id=1)
        after_member = Member.objects.get(username="jokke")

        self.assertEqual(before.bought, after.bought)
        self.assertEqual(before_member.balance, after_member.balance)


class TransactionTests(TestCase):
    def test_pay_transaction_change_neg(self):
        transaction = PayTransaction(100)
        self.assertEqual(transaction.change(), -100)

    def test_pay_transaction_add(self):
        transaction = PayTransaction(90)
        transaction.add(10)
        self.assertEqual(transaction.change(), -100)

    def test_get_transaction_change_pos(self):
        transaction = GetTransaction(100)
        self.assertEqual(transaction.change(), 100)

    def test_get_transaction_change_add(self):
        transaction = GetTransaction(90)
        transaction.add(10)
        self.assertEqual(transaction.change(), 100)


class OrderTest(TestCase):
    def setUp(self):
        self.member = Member.objects.create(balance=100)
        self.room = Room.objects.create(name="room")
        self.product = Product.objects.create(id=1, name="øl", price=10,
                                              active=True)

    def test_order_fromproducts(self):
        products = [
            self.product,
            self.product,
        ]
        order = Order.from_products(self.member, self.room, products)
        self.assertEqual(
            list(Counter(products).items()),
            [(item.product, item.count) for item in order.items]
        )

    def test_order_total_single_item(self):
        order = Order(self.member, self.room)

        item = OrderItem(self.product, order, 1)
        order.items.add(item)

        self.assertEqual(order.total(), 10)

    def test_order_total_multi_item(self):
        order = Order(self.member, self.room)

        item = OrderItem(self.product, order, 2)
        order.items.add(item)

        self.assertEqual(order.total(), 20)

    @patch('stregsystem.models.Member.fulfill')
    def test_order_execute_single_transaction(self, fulfill):
        order = Order(self.member, self.room)

        item = OrderItem(self.product, order, 1)
        order.items.add(item)

        order.execute()

        fulfill.assert_called_once_with(PayTransaction(10))

    @patch('stregsystem.models.Member.fulfill')
    def test_order_execute_multi_transaction(self, fulfill):
        order = Order(self.member, self.room)

        item = OrderItem(self.product, order, 2)
        order.items.add(item)

        order.execute()

        fulfill.assert_called_once_with(PayTransaction(20))

    @patch('stregsystem.models.Member.fulfill')
    def test_order_execute_single_no_remaining(self, fulfill):
        self.product.bought = 1
        self.product.quantity = 1
        order = Order(self.member, self.room)

        item = OrderItem(self.product, order, 1)
        order.items.add(item)

        with self.assertRaises(NoMoreInventoryError):
            order.execute()

        fulfill.was_not_called()

    @patch('stregsystem.models.Member.fulfill')
    def test_order_execute_multi_some_remaining(self, fulfill):
        self.product.bought = 1
        self.product.quantity = 2
        order = Order(self.member, self.room)

        item = OrderItem(self.product, order, 2)
        order.items.add(item)

        with self.assertRaises(NoMoreInventoryError):
            order.execute()

        fulfill.was_not_called()

    @patch('stregsystem.models.Member.can_fulfill')
    @patch('stregsystem.models.Member.fulfill')
    def test_order_execute_no_money(self, fulfill, can_fulfill):
        can_fulfill.return_value = False
        order = Order(self.member, self.room)

        item = OrderItem(self.product, order, 2)
        order.items.add(item)

        with self.assertRaises(StregForbudError):
            order.execute()

        fulfill.was_not_called()


class PaymentTests(TestCase):
    def setUp(self):
        self.member = Member.objects.create(
            username="jon",
            balance=100
        )

    @patch("stregsystem.models.Member.make_payment")
    def test_payment_save_not_saved(self, make_payment):
        payment = Payment(
            member=self.member,
            amount=100
        )

        payment.save()

        make_payment.assert_called_once_with(100)

    @patch("stregsystem.models.Member.make_payment")
    def test_payment_save_already_saved(self, make_payment):
        payment = Payment(
            member=self.member,
            amount=100
        )
        payment.save()
        make_payment.reset_mock()

        payment.save()

        make_payment.assert_not_called()

    @patch("stregsystem.models.Member.make_payment")
    def test_payment_delete_already_saved(self, make_payment):
        payment = Payment(
            member=self.member,
            amount=100
        )
        payment.save()
        make_payment.reset_mock()

        payment.delete()

        make_payment.assert_called_once_with(-100)

    @patch("stregsystem.models.Member.make_payment")
    def test_payment_delete_not_saved(self, make_payment):
        payment = Payment(
            member=self.member,
            amount=100
        )

        with self.assertRaises(AssertionError):
            payment.delete()


class ProductTests(TestCase):
    def test_is_active_active(self):
        product = Product(
            active=True,
        )

        self.assertTrue(product.is_active())

    def test_is_active_active_not_expired(self):
        product = Product(
            active=True,
            deactivate_date=(timezone.now()
                             + datetime.timedelta(hours=1))
        )

        self.assertTrue(product.is_active())

    def test_is_active_active_expired(self):
        product = Product(
            active=True,
            deactivate_date=(timezone.now()
                             - datetime.timedelta(hours=1))
        )

        self.assertFalse(product.is_active())

    def test_is_active_active_out_of_stock(self):
        product = Product(
            active=True,
            quantity=1,
            bought=1
        )

        self.assertFalse(product.is_active())

    def test_is_active_active_in_stock(self):
        product = Product(
            active=True,
            quantity=2,
            bought=1
        )

        self.assertTrue(product.is_active())

    def test_is_active_deactive(self):
        product = Product(
            active=False,
        )

        self.assertFalse(product.is_active())

    def test_is_active_deactive_expired(self):
        product = Product(
            active=False,
            deactivate_date=(timezone.now()
                             - datetime.timedelta(hours=1))
        )

        self.assertFalse(product.is_active())

    def test_is_active_deactive_out_of_stock(self):
        product = Product(
            active=False,
            quantity=1,
            bought=1
        )

        self.assertFalse(product.is_active())

    def test_is_active_deactive_in_stock(self):
        product = Product(
            active=False,
            quantity=2,
            bought=1
        )

        self.assertFalse(product.is_active())


class SaleTests(TestCase):
    def setUp(self):
        self.member = Member.objects.create(
            username="jon",
            balance=100
        )
        self.product = Product.objects.create(
            name="beer",
            price=1.0,
            active=True,
        )

    def test_sale_save_not_saved(self):
        sale = Sale(
            member=self.member,
            product=self.product,
            price=100
        )

        sale.save()

        self.assertIsNotNone(sale.id)

    def test_sale_save_already_saved(self):
        sale = Sale(
            member=self.member,
            product=self.product,
            price=100
        )
        sale.save()

        with self.assertRaises(RuntimeError):
            sale.save()

    def test_sale_delete_not_saved(self):
        sale = Sale(
            member=self.member,
            product=self.product,
            price=100
        )

        with self.assertRaises(RuntimeError):
            sale.delete()

    def test_sale_delete_already_saved(self):
        sale = Sale(
            member=self.member,
            product=self.product,
            price=100
        )
        sale.save()

        sale.delete()

        self.assertIsNone(sale.id)


class MemberTests(TestCase):
    def test_fulfill_pay_transaction(self):
        member = Member(
            balance=100
        )
        transaction = PayTransaction(10)
        member.fulfill(transaction)

        self.assertEqual(member.balance, 90)

    def test_fulfill_pay_transaction_no_money(self):
        member = Member(
            balance=2
        )
        transaction = PayTransaction(10)
        with self.assertRaises(StregForbudError) as c:
            member.fulfill(transaction)

        self.assertTrue(c.exception)
        self.assertEqual(member.balance, 2)

    def test_fulfill_pay_transaction_rollback(self):
        member = Member(
            balance=2
        )
        transaction = PayTransaction(10)
        member.rollback(transaction)

        self.assertEqual(member.balance, 12)

    def test_fulfill_check_transaction_has_money(self):
        member = Member(
            balance=10
        )
        transaction = PayTransaction(10)

        has_money = member.can_fulfill(transaction)

        self.assertTrue(has_money)

    def test_fulfill_check_transaction_no_money(self):
        member = Member(
            balance=2
        )
        transaction = PayTransaction(10)

        has_money = member.can_fulfill(transaction)

        self.assertFalse(has_money)

    def test_make_payment_positive(self):
        member = Member(
            balance=100
        )

        member.make_payment(10)

        self.assertEqual(member.balance, 110)

    def test_make_payment_negative(self):
        member = Member(
            balance=100
        )

        member.make_payment(-10)

        self.assertEqual(member.balance, 90)


class ProductActivatedListFilterTests(TestCase):
    def setUp(self):
        Product.objects.create(
            name="active_dec_none",
            price=1.0, active=True,
            deactivate_date=None
        )
        Product.objects.create(
            name="active_dec_future",
            price=1.0,
            active=True,
            deactivate_date=(datetime.datetime.now()
                             + datetime.timedelta(hours=1))
        )
        Product.objects.create(
            name="active_dec_past",
            price=1.0,
            active=True,
            deactivate_date=(datetime.datetime.now()
                             - datetime.timedelta(hours=1))
        )

        Product.objects.create(
            name="deactivated_dec_none",
            price=1.0,
            active=False,
            deactivate_date=None
        )
        Product.objects.create(
            name="deactivated_dec_future",
            price=1.0,
            active=False,
            deactivate_date=(datetime.datetime.now()
                             + datetime.timedelta(hours=1))
        )
        Product.objects.create(
            name="deactivated_dec_past",
            price=1.0,
            active=False,
            deactivate_date=(datetime.datetime.now()
                             - datetime.timedelta(hours=1))
        )
        Product.objects.create(
            name="active_none_left",
            price=1.0,
            active=True,
            bought=2,
            quantity=2,
        )
        Product.objects.create(
            name="active_some_left",
            price=1.0,
            active=True,
            bought=0,
            quantity=2,
        )

    def test_active_trivial(self):
        fy = admin.ProductActivatedListFilter(
            None,
            {'activated': 'Yes'},
            Product,
            ProductAdmin
        )
        qy = list(fy.queryset(None, Product.objects.all()))
        fn = admin.ProductActivatedListFilter(
            None,
            {'activated': 'No'},
            Product,
            ProductAdmin
        )
        qn = list(fn.queryset(None, Product.objects.all()))

        self.assertIn(Product.objects.get(name="active_dec_none"), qy)
        self.assertNotIn(Product.objects.get(name="active_dec_none"), qn)

    def test_active_deac_future(self):
        fy = admin.ProductActivatedListFilter(
            None,
            {'activated': 'Yes'},
            Product,
            ProductAdmin
        )
        qy = list(fy.queryset(None, Product.objects.all()))
        fn = admin.ProductActivatedListFilter(
            None,
            {'activated': 'No'},
            Product,
            ProductAdmin
        )
        qn = list(fn.queryset(None, Product.objects.all()))

        self.assertIn(Product.objects.get(name="active_dec_future"), qy)
        self.assertNotIn(Product.objects.get(name="active_dec_future"), qn)

    def test_active_deac_past(self):
        fy = admin.ProductActivatedListFilter(
            None,
            {'activated': 'Yes'},
            Product,
            ProductAdmin
        )
        qy = list(fy.queryset(None, Product.objects.all()))
        fn = admin.ProductActivatedListFilter(
            None,
            {'activated': 'No'},
            Product,
            ProductAdmin
        )
        qn = list(fn.queryset(None, Product.objects.all()))

        self.assertNotIn(Product.objects.get(name="active_dec_past"), qy)
        self.assertIn(Product.objects.get(name="active_dec_past"), qn)

    def test_inactive_trivial(self):
        fy = admin.ProductActivatedListFilter(
            None,
            {'activated': 'Yes'},
            Product,
            ProductAdmin
        )
        qy = list(fy.queryset(None, Product.objects.all()))
        fn = admin.ProductActivatedListFilter(
            None,
            {'activated': 'No'},
            Product,
            ProductAdmin
        )
        qn = list(fn.queryset(None, Product.objects.all()))

        self.assertNotIn(Product.objects.get(name="deactivated_dec_none"), qy)
        self.assertIn(Product.objects.get(name="deactivated_dec_none"), qn)

    def test_inactive_deac_future(self):
        fy = admin.ProductActivatedListFilter(
            None,
            {'activated': 'Yes'},
            Product,
            ProductAdmin
        )
        qy = list(fy.queryset(None, Product.objects.all()))
        fn = admin.ProductActivatedListFilter(
            None,
            {'activated': 'No'},
            Product,
            ProductAdmin
        )
        qn = list(fn.queryset(None, Product.objects.all()))

        self.assertNotIn(
            Product.objects.get(name="deactivated_dec_future"),
            qy
        )
        self.assertIn(Product.objects.get(name="deactivated_dec_future"), qn)

    def test_inactive_deac_past(self):
        fy = admin.ProductActivatedListFilter(
            None,
            {'activated': 'Yes'},
            Product,
            ProductAdmin
        )
        qy = list(fy.queryset(None, Product.objects.all()))
        fn = admin.ProductActivatedListFilter(
            None,
            {'activated': 'No'},
            Product,
            ProductAdmin
        )
        qn = list(fn.queryset(None, Product.objects.all()))

        self.assertNotIn(Product.objects.get(name="deactivated_dec_past"), qy)
        self.assertIn(Product.objects.get(name="deactivated_dec_past"), qn)

    def test_active_none_left(self):
        fy = admin.ProductActivatedListFilter(
            None,
            {'activated': 'Yes'},
            Product,
            ProductAdmin
        )
        qy = list(fy.queryset(None, Product.objects.all()))
        fn = admin.ProductActivatedListFilter(
            None,
            {'activated': 'No'},
            Product,
            ProductAdmin
        )
        qn = list(fn.queryset(None, Product.objects.all()))

        self.assertNotIn(Product.objects.get(name="active_none_left"), qy)
        self.assertIn(Product.objects.get(name="active_none_left"), qn)

    def test_active_some_left(self):
        fy = admin.ProductActivatedListFilter(
            None,
            {'activated': 'Yes'},
            Product,
            ProductAdmin
        )
        qy = list(fy.queryset(None, Product.objects.all()))
        fn = admin.ProductActivatedListFilter(
            None,
            {'activated': 'No'},
            Product,
            ProductAdmin
        )
        qn = list(fn.queryset(None, Product.objects.all()))

        self.assertIn(Product.objects.get(name="active_some_left"), qy)
        self.assertNotIn(Product.objects.get(name="active_some_left"), qn)


class QuickbuyParserTests(TestCase):
    def setUp(self):
        self.test_username = 'test'

    def test_username_only(self):
        buy_string = self.test_username

        username, products = parser.parse(buy_string)

        self.assertEqual(self.test_username, username)
        self.assertEqual(len(products), 0)

    def test_single_buy(self):
        product_ids = [42]
        buy_string = self.test_username + ' 42'

        username, products = parser.parse(buy_string)

        self.assertEqual(username, self.test_username)
        self.assertEqual(len(products), 1)
        assertCountEqual(self, product_ids, products)

    def test_multi_buy(self):
        product_ids = [42, 1337]
        buy_string = self.test_username + " 42 1337"

        username, products = parser.parse(buy_string)

        self.assertEqual(username, self.test_username)
        self.assertEqual(len(products), len(product_ids))
        assertCountEqual(self, product_ids, products)

    def test_multi_buy_repeated(self):
        product_ids = [42, 42]
        buy_string = self.test_username + " 42 42"

        username, products = parser.parse(buy_string)

        self.assertEqual(username, self.test_username)
        self.assertEqual(len(products), len(product_ids))
        assertCountEqual(self, product_ids, products)

    def test_multi_buy_quantifier(self):
        product_ids = [42, 42, 1337, 1337, 1337]
        buy_string = self.test_username + " 42:2 1337:3"

        username, products = parser.parse(buy_string)

        self.assertEqual(username, self.test_username)
        self.assertEqual(len(products), len(product_ids))
        assertCountEqual(self, product_ids, products)

    def test_zero_quantifier(self):
        buy_string = self.test_username + " 42:0"

        username, products = parser.parse(buy_string)

        self.assertEqual(username, self.test_username)
        self.assertEqual(len(products), 0)

    def test_negative_quantifier(self):
        buy_string = self.test_username + ' 42:-1 1337:3'
        with self.assertRaises(parser.QuickBuyError):
            parser.parse(buy_string)

    def test_missing_quantifier(self):
        buy_string = self.test_username + ' 42: 1337:3'
        with self.assertRaises(parser.QuickBuyError):
            parser.parse(buy_string)

    def test_invalid_quantifier(self):
        buy_string = self.test_username + ' 42:a 1337:3'
        with self.assertRaises(parser.QuickBuyError):
            parser.parse(buy_string)

    def test_invalid_productId(self):
        buy_string = self.test_username + ' a:2 1337:3'
        with self.assertRaises(parser.QuickBuyError):
            parser.parse(buy_string)
