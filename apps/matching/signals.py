from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.db.models import F

from .models import Match, ProfileView
from apps.users.models import Profile


@receiver(post_save, sender=Match)
def update_match_count_on_save(sender, instance, created, **kwargs):
    """
    Update total_matches when a mutual match is created.
    """
    if instance.is_mutual:
        # Update both users' match counts
        Profile.objects.filter(user=instance.user).update(
            total_matches=F('total_matches') + 1
        )
        Profile.objects.filter(user=instance.matched_user).update(
            total_matches=F('total_matches') + 1
        )


@receiver(post_delete, sender=Match)
def update_match_count_on_delete(sender, instance, **kwargs):
    """
    Decrease total_matches when a match is deleted.
    """
    if instance.is_mutual:
        # Decrease both users' match counts (but not below 0)
        for user in [instance.user, instance.matched_user]:
            profile = Profile.objects.filter(user=user).first()
            if profile and profile.total_matches > 0:
                Profile.objects.filter(user=user).update(
                    total_matches=F('total_matches') - 1
                )


@receiver(post_save, sender=ProfileView)
def update_view_count(sender, instance, created, **kwargs):
    """
    Increment profile_views when someone views a profile.
    """
    if created:
        Profile.objects.filter(user=instance.viewed_profile).update(
            profile_views=F('profile_views') + 1
        )