from django.apps import AppConfig


class DragonWishConfig(AppConfig):
    name = "dragonwish"
    verbose_name = "Dragon wish"
    default_auto_field = "django.db.models.BigAutoField"
    dpy_package = "dragonwish.wish_ext"
