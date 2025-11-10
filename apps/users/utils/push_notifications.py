# apps/users/utils/push_notifications.py (Updated)

import requests
import json
from typing import List, Dict, Any
from apps.users.models import DeviceToken
# Import User and Profile models here or pass the photo URL directly.
# Assuming you already have access to the models for illustration.
from apps.users.models import User, Profile 

EXPO_PUSH_URL = 'https://exp.host/--/api/v2/push/send'

# 🎯 TODO: Replace this with the actual URL of your app's logo
APP_ICON_URL = 'https://i.pinimg.com/736x/df/c7/4e/dfc74efc5fdaacc9f50beb5a795aa46b.jpg'

def send_push_notification(
    user_id: str,
    title: str,
    body: str,
    data: Dict[str, Any] = None
) -> bool:
    """
    Send push notification to a specific user.
    
    Args:
        user_id: User UUID
        title: Notification title
        body: Notification body
        data: Additional data to include (can contain 'imageUrl' for rich media)
    
    Returns:
        bool: True if sent successfully
    """
    data = data or {}
    
    # 🚀 FIX: Determine the final image URL. 
    # Prioritize 'imageUrl' from the input data, otherwise use the APP_ICON_URL as fallback.
    final_image_url = data.get('imageUrl', APP_ICON_URL)
    
    try:
        # Get user's active device tokens
        tokens = DeviceToken.objects.filter(
            user__id=user_id,
            is_active=True
        ).values_list('token', flat=True)
        
        if not tokens:
            print(f'No active tokens for user {user_id}')
            return False
        
        # Prepare notification payload
        messages = []
        for token in tokens:
            
            # The 'imageUrl' key is what the rich notification extension looks for
            final_data_payload = {
                **data,  # Include all original data first (type, username, etc.)
                'imageUrl': final_image_url, # Add/overwrite the imageUrl field
            }
            
            messages.append({
                'to': token,
                'sound': 'default',
                'title': title,
                'body': body,
                'data': final_data_payload,
                'priority': 'high',
            })
        
        # Send to Expo Push Notification service
        response = requests.post(
            EXPO_PUSH_URL,
            headers={
                'Accept': 'application/json',
                'Accept-encoding': 'gzip, deflate',
                'Content-Type': 'application/json',
            },
            data=json.dumps(messages)
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f'Push notification sent: {result}')
            return True
        else:
            print(f'Failed to send notification: {response.text}')
            return False
            
    except Exception as e:
        print(f'Error sending push notification: {e}')
        return False


# --- Helper to get user photo URL (reused from previous answer) ---

def get_user_photo_url(user_id: str) -> str | None:
    """Helper to get the primary photo URL for a user."""
    try:
        user = User.objects.get(id=user_id)
        # Fetch the primary photo URL
        photo = user.profile.photos.filter(is_primary=True).first() or user.profile.photos.first()
        if photo and photo.image:
            # IMPORTANT: Ensure this returns a full, absolute HTTPS URL
            return photo.image.url
        return None
    except (User.DoesNotExist, AttributeError):
        return None

# --- Updated call functions ---

def send_like_notification(liker_username: str, liked_user_id: str, liker_user_id: str):
    """Send notification when someone likes you."""
    # Get the photo of the person who liked (the liker)
    image_url = get_user_photo_url(liker_user_id)
    
    data_payload = {
        'type': 'like',
        'username': liker_username,
    }
    if image_url:
        data_payload['imageUrl'] = image_url
        
    send_push_notification(
        user_id=liked_user_id,
        title='New Like! 💖',
        body=f'{liker_username} liked you!',
        data=data_payload
    )


def send_match_notification(matched_username: str, user_id: str, match_id: str, matched_user_id: str):
    """Send notification when there's a mutual match."""
    # Get the photo of the person you matched with
    image_url = get_user_photo_url(matched_user_id)
    
    data_payload = {
        'type': 'match',
        'username': matched_username,
        'matchId': match_id,
    }
    if image_url:
        data_payload['imageUrl'] = image_url
        
    send_push_notification(
        user_id=user_id,
        title="It's a Match! 🎉",
        body=f"You and {matched_username} liked each other!",
        data=data_payload
    )


def send_message_notification(sender_username: str, receiver_id: str, message_preview: str, sender_id: str):
    """Send notification for new message."""
    # Get the photo of the person who sent the message
    image_url = get_user_photo_url(sender_id)
    
    data_payload = {
        'type': 'message',
        'username': sender_username,
    }
    if image_url:
        data_payload['imageUrl'] = image_url

    send_push_notification(
        user_id=receiver_id,
        title=f'New message from {sender_username}',
        body=message_preview[:50] + '...' if len(message_preview) > 50 else message_preview,
        data=data_payload
    )