from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.users.models import Story

class Command(BaseCommand):
    help = 'Delete expired stories (older than 24 hours)'

    def handle(self, *args, **options):
        now = timezone.now()
        
        expired_stories = Story.objects.filter(expires_at__lte=now)
        count = expired_stories.count()
        
        if count > 0:
            expired_stories.delete()
            self.stdout.write(
                self.style.SUCCESS(f'✅ Deleted {count} expired stories')
            )
        else:
            self.stdout.write(
                self.style.SUCCESS('✓ No expired stories to delete')
            )