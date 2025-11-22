from django.apps import AppConfig

class MatchingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.matching'

    def ready(self):
        """
        Import signals when app is ready.
        """
        import apps.matching.signals