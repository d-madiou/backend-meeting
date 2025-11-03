from django.core.management.base import BaseCommand
from apps.users.models import Interest

class Command(BaseCommand):
    help = 'Create a sample interests'

    def handle(self, *args, **kwargs):
        interests = [
            'Travel', 'Music', 'Movies', 'Photography', 'Cooking',
            'Reading', 'Gaming', 'Sports', 'Fitness', 'Yoga',
            'Dancing', 'Art', 'Fashion', 'Technology', 'Science',
            'Nature', 'Hiking', 'Beach', 'Coffee', 'Wine',
            'Pets', 'Volunteering', 'Writing', 'Languages', 'History',
            'Politics', 'Meditation', 'Surfing', 'Cycling', 'Running',
        ]

        for interest_name in interests:
            Interest.objects.get_or_create(name=interest_name)
            self.stdout.write(self.style.SUCCESS(f'Interest "{interest_name}" created or already exists.'))

        self.stdout.write(self.style.SUCCESS(f'\n Sample interests {len(interests)} created successfully.'))