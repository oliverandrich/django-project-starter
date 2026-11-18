from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractUser
from django.db import IntegrityError
from django.test import SimpleTestCase, TestCase
from model_bakery import baker

from tests.utils import PACKAGE


class UserModelTest(SimpleTestCase):
    def test_user_model_is_the_project_model(self):
        # A later switch of AUTH_USER_MODEL breaks the migration history.
        user_model = get_user_model()
        self.assertEqual(user_model._meta.label, f"{PACKAGE}.User")
        self.assertTrue(issubclass(user_model, AbstractUser))

    def test_user_model_is_in_the_admin(self):
        self.assertTrue(admin.site.is_registered(get_user_model()))


class UserEmailTest(TestCase):
    def test_an_address_belongs_to_one_account_whatever_its_case(self):
        baker.make(get_user_model(), email="kim@customer.example")
        with self.assertRaises(IntegrityError):
            baker.make(get_user_model(), email="Kim@Customer.example")

    def test_accounts_without_an_address_do_not_collide(self):
        baker.make(get_user_model(), email="", _quantity=2)
