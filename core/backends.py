import random
import string
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model

User = get_user_model()


def email_to_username(email):
    """Convert email to a unique username, handling +aliases and dots."""
    base = email.replace('@', '_at_').replace('+', '_plus_').replace('.', '_')
    suffix = ''.join(random.choices(string.digits, k=4))
    return f"{base}_{suffix}"


class EmailOrUsernameBackend(ModelBackend):
    """Authenticate with either email or username. Allows inactive users (for email verification flow)."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        if not username or not password:
            return None

        if '@' in username:
            lookup = {'email': username}
        else:
            lookup = {'username': username}

        try:
            user = User.objects.get(**lookup)
            if user.check_password(password):
                return user
        except User.DoesNotExist:
            return None
        return None

    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
