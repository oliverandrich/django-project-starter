from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.functions import Lower


class User(AbstractUser):
    """The account model. It exists before the first migration, so it can gain fields later."""

    class Meta(AbstractUser.Meta):
        constraints = [
            # One account per address, whatever its case: logins by email must find exactly one.
            models.UniqueConstraint(
                Lower("email"), condition=~models.Q(email=""), name="user_email_unique"
            ),
        ]
