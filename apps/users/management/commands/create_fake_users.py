from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from apps.users.models import Profile, ProfilePhoto, Interest, ProfileInterest
from faker import Faker
from datetime import datetime, timedelta
import random

User = get_user_model()
fake = Faker()

class Command(BaseCommand):
    help = 'Create fake users with complete profiles for testing'

    def add_arguments(self, parser):
        parser.add_argument(
            '--count',
            type=int,
            default=20,
            help='Number of fake users to create'
        )

    def handle(self, *args, **options):
        count = options['count']
        
        # Get or create interests first
        interest_names = [
            'Travel', 'Music', 'Movies', 'Photography', 'Cooking',
            'Reading', 'Gaming', 'Sports', 'Fitness', 'Yoga',
            'Dancing', 'Art', 'Fashion', 'Technology', 'Coffee'
        ]
        
        interests = []
        for name in interest_names:
            interest, _ = Interest.objects.get_or_create(name=name)
            interests.append(interest)
        
        self.stdout.write(self.style.SUCCESS(f'✓ Created {len(interests)} interests'))
        
        # Create fake users
        for i in range(count):
            try:
                # Create user
                username = fake.user_name() + str(random.randint(100, 999))
                email = f"{username}@example.com"
                
                user = User.objects.create_user(
                    email=email,
                    username=username,
                    password='testpass123'
                )
                
                # Create profile
                profile = Profile.objects.get(user=user)
                
                # Fill profile data
                gender = random.choice(['M', 'F'])
                profile.bio = fake.text(max_nb_chars=200)
                profile.birth_date = fake.date_of_birth(minimum_age=20, maximum_age=45)
                profile.gender = gender
                profile.city = fake.city()
                profile.country = random.choice(['Guinea', 'Senegal', 'Mali', 'Cote d\'Ivoire'])
                profile.relationship_goal = random.choice(['casual', 'serious', 'friendship', 'marriage'])
                profile.looking_for_gender = random.choice(['M', 'F'])
                profile.min_age_preference = random.randint(20, 30)
                profile.max_age_preference = random.randint(35, 50)
                profile.max_distance_km = random.randint(20, 100)
                profile.save()
                
                # Add random interests (3-7)
                num_interests = random.randint(3, 7)
                user_interests = random.sample(interests, num_interests)
                
                for interest in user_interests:
                    ProfileInterest.objects.create(
                        profile=profile,
                        interest=interest,
                        passion_level=random.randint(2, 5)
                    )
                
                # Calculate completion
                profile.calculate_completion_percentage()
                
                self.stdout.write(
                    self.style.SUCCESS(
                        f'✓ Created user: {username} ({profile.age} years old, {gender})'
                    )
                )
                
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'✗ Failed to create user: {str(e)}')
                )
        
        self.stdout.write(
            self.style.SUCCESS(f'\n✅ Successfully created {count} fake users!')
        )