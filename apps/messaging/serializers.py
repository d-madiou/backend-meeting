"""
Messaging Serializers
======================
"""

from rest_framework import serializers
from django.conf import settings
from .models import Message, Conversation, CoinWallet, CoinTransaction, DailyMessageQuota
from apps.users.serializers import UserBriefSerializer


# ============================================================================
# MESSAGING SERIALIZERS
# ============================================================================

class MessageSerializer(serializers.ModelSerializer):
    """
    Serializer for Message model.
    """
    
    sender = UserBriefSerializer(read_only=True)
    receiver = UserBriefSerializer(read_only=True)
    
    class Meta:
        model = Message
        fields = [
            'uuid', 'sender', 'receiver', 'content',
            'coin_cost', 'is_read', 'read_at', 'created_at'
        ]
        read_only_fields = [
            'uuid', 'coin_cost', 'is_read', 'read_at', 'created_at'
        ]


class MessageCreateSerializer(serializers.Serializer):
    """
    Serializer for creating messages.
    
    Design: Separate creation serializer for custom validation.
    """
    
    receiver_uuid = serializers.UUIDField(required=True)
    content = serializers.CharField(
        required=True,
        max_length=1000,
        trim_whitespace=True
    )
    
    def validate_content(self, value):
        """
        Validate message content.
        """
        if not value or not value.strip():
            raise serializers.ValidationError('Message cannot be empty.')
        
        return value.strip()


class ConversationSerializer(serializers.ModelSerializer):
    """
    Serializer for Conversation model.
    """
    
    other_user = serializers.SerializerMethodField()
    latest_message = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Conversation
        fields = [
            'uuid', 'other_user', 'latest_message',
            'unread_count', 'created_at', 'last_message_at'
        ]
        read_only_fields = ['uuid', 'created_at', 'last_message_at']
    
    def get_other_user(self, obj):
        """
        Get the other participant (not the current user).
        """
        request = self.context.get('request')
        if request and request.user:
            other_user = obj.get_other_participant(request.user)
            return UserBriefSerializer(other_user, context=self.context).data
        return None
    
    def get_latest_message(self, obj):
        """
        Get the most recent message in conversation.
        """
        # Use prefetched data if available
        if hasattr(obj, 'latest_message') and obj.latest_message:
            message = obj.latest_message[0]
            return {
                'content': message.content,
                'created_at': message.created_at,
                'is_read': message.is_read,
                'sender_username': message.sender.username
            }
        
        # Fallback to query
        latest = obj.messages.order_by('-created_at').first()
        if latest:
            return {
                'content': latest.content,
                'created_at': latest.created_at,
                'is_read': latest.is_read,
                'sender_username': latest.sender.username
            }
        return None
    
    def get_unread_count(self, obj):
        """
        Get count of unread messages for current user.
        """
        request = self.context.get('request')
        if request and request.user:
            return obj.messages.filter(
                receiver=request.user,
                is_read=False
            ).count()
        return 0


class CoinWalletSerializer(serializers.ModelSerializer):
    """
    Serializer for CoinWallet model.
    """
    
    class Meta:
        model = CoinWallet
        fields = [
            'balance', 'total_earned', 'total_spent',
            'total_purchased', 'created_at', 'updated_at'
        ]
        read_only_fields = fields


class CoinTransactionSerializer(serializers.ModelSerializer):
    """
    Serializer for CoinTransaction model.
    """
    
    class Meta:
        model = CoinTransaction
        fields = [
            'uuid', 'amount', 'transaction_type',
            'balance_after', 'description', 'created_at'
        ]
        read_only_fields = fields
