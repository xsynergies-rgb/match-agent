from django.contrib.auth.base_user import BaseUserManager

from .phone import InvalidPhone, normalize_phone


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, phone, password, **extra_fields):
        try:
            phone = normalize_phone(phone)
        except InvalidPhone as error:
            raise ValueError(str(error.message)) from error
        user = self.model(phone=phone, **extra_fields)
        if password:
            user.set_password(password)
        else:
            # Players sign in with a phone code only; there is no password to guess.
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_user(self, phone, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(phone, password, **extra_fields)

    def create_superuser(self, phone, password=None, **extra_fields):
        extra_fields["is_staff"] = True
        extra_fields["is_superuser"] = True
        if not password:
            raise ValueError("A superuser needs a password to sign in to /admin/.")
        return self._create_user(phone, password, **extra_fields)

    def get_by_natural_key(self, phone):
        # The admin login form passes whatever was typed; match it the way sign-in does.
        try:
            phone = normalize_phone(phone)
        except InvalidPhone:
            raise self.model.DoesNotExist from None
        return self.get(phone=phone)
