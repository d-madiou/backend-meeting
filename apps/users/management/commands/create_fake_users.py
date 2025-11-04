from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from apps.users.models import Profile, Interest, ProfileInterest
from faker import Faker
import random
from datetime import date, timedelta

User = get_user_model()
fake = Faker()

class Command(BaseCommand):
    help = 'Create fake users with profiles for testing'

    def add_arguments(self, parser):
        parser.add_argument(
            '--count',
            type=int,
            default=20,
            help='Number of fake users to create'
        )

    def handle(self, *args, **options):
        count = options['count']
        
        # Get all interests
        interests = list(Interest.objects.all())
        if not interests:
            self.stdout.write(self.style.WARNING('No interests found. Run create_interests first.'))
            return
        
        self.stdout.write(f'Creating {count} fake users...')
        
        for i in range(count):
            try:
                # Create user
                username = fake.user_name() + str(random.randint(1000, 9999))
                email = f"{username}@example.com"
                
                user = User.objects.create_user(
                    email=email,
                    username=username,
                    password='testpassword123'
                )
                
                # Create profile
                gender = random.choice(['M', 'F', 'O'])
                birth_date = fake.date_of_birth(minimum_age=18, maximum_age=45)
                
                profile = Profile.objects.create(user=user)
                profile.bio = fake.text(max_nb_chars=200)
                profile.birth_date = birth_date
                profile.gender = gender
                profile.city = fake.city()
                profile.country = random.choice(['Guinea', 'Senegal', 'Mali', 'Nigeria'])
                profile.relationship_goal = random.choice(['casual', 'serious', 'friendship', 'marriage'])
                profile.looking_for_gender = random.choice(['M', 'F', 'O'])
                profile.min_age_preference = random.randint(18, 30)
                profile.max_age_preference = random.randint(30, 50)
                profile.max_distance_km = random.randint(10, 100)
                profile.save()
                
                # Add random interests
                user_interests = random.sample(interests, k=random.randint(3, 8))
                for interest in user_interests:
                    ProfileInterest.objects.create(
                        profile=profile,
                        interest=interest,
                        passion_level=random.randint(2, 5)
                    )
                
                # Calculate completion
                profile.calculate_completion_percentage()
                
                self.stdout.write(self.style.SUCCESS(f'✓ Created: {username}'))
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'✗ Error: {str(e)}'))
        
        self.stdout.write(self.style.SUCCESS(f'\n✅ Successfully created {count} fake users'))