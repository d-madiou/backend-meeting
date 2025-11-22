from django.core.management.base import BaseCommand
from django.db.models import Count
from apps.users.models import Profile
from apps.matching.models import Match, ProfileView
from apps.messaging.models import Message


class Command(BaseCommand):
    help = 'Recalculate profile statistics for all users'

    def handle(self, *args, **options):
        profiles = Profile.objects.all()
        total = profiles.count()
        
        self.stdout.write(f'Recalculating stats for {total} profiles...')
        
        updated_count = 0
        for profile in profiles:
            # Count mutual matches
            matches_count = Match.objects.filter(
                user=profile.user,
                is_mutual=True
            ).count()
            
            # Count profile views
            views_count = ProfileView.objects.filter(
                viewed_profile=profile.user
            ).count()
            
            # Count messages sent
            messages_count = Message.objects.filter(
                sender=profile.user
            ).count()
            
            # Update profile
            profile.total_matches = matches_count
            profile.profile_views = views_count
            profile.total_messages_sent = messages_count
            profile.save(update_fields=[
                'total_matches', 
                'profile_views', 
                'total_messages_sent'
            ])
            
            updated_count += 1
            
            if updated_count % 50 == 0:
                self.stdout.write(f'Processed {updated_count}/{total}...')
        
        self.stdout.write(self.style.SUCCESS(
            f'\n✅ Successfully updated stats for {updated_count} profiles'
        ))
        
        # Show summary
        self.stdout.write('\nSummary:')
        total_matches = Profile.objects.aggregate(
            total=Count('total_matches')
        )['total']
        total_views = Profile.objects.aggregate(
            total=Count('profile_views')
        )['total']
        
        self.stdout.write(f'Total matches: {total_matches}')
        self.stdout.write(f'Total views: {total_views}')