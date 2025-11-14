"""
Messaging Service Layer
========================
Demonstrates:
- Business logic separation from views
- Transaction management for data consistency
- Complex validation logic
- Coin-based monetization implementation

Key Principle: Views should be thin - they handle HTTP, services handle business logic.
"""

from django.db import transaction
from django.core.exceptions import ValidationError, PermissionDenied
from django.conf import settings
from django.utils import timezone
from django.core.cache import cache
from datetime import date
import logging

from .models import (
    Message, Conversation, CoinWallet, 
    CoinTransaction, DailyMessageQuota
)
from apps.matching.models import Block

logger = logging.getLogger(__name__)


# ============================================================================
# MESSAGE SERVICE
# ============================================================================

class MessageService:
    """
    Encapsulates all business logic for messaging operations.
    
    Design Pattern: Service Layer
    - Keeps views thin and focused on HTTP handling
    - Makes business logic reusable and testable
    - Centralizes transaction management
    """
    
    @staticmethod
    def can_send_message(sender, receiver):
        """
        Check if sender can send a message to receiver.
        
        Validation Rules:
        1. Users must not have blocked each other
        2. Sender cannot message themselves
        3. Both users must be active
        
        Returns:
            tuple: (bool, str) - (can_send, reason_if_not)
        """
        # Check if messaging self
        if sender.id == receiver.id:
            return False, "Cannot send messages to yourself"
        
        # Check if either user is inactive
        if not sender.is_active or not receiver.is_active:
            return False, "One or both users are inactive"
        
        # Check for blocks
        if Block.is_blocked(sender, receiver):
            return False, "Cannot send message due to block"
        
        return True, ""
    
    @staticmethod
    def calculate_message_cost(sender, conversation):
        """
        Calculate coin cost for sending a message.
        
        Business Rule:
        - First 3 messages per day per conversation: FREE
        - Subsequent messages: 1 coin each
        
        Args:
            sender: User sending the message
            conversation: Conversation object
        
        Returns:
            int: Number of coins required (0 if free)
        """
        # Get today's quota
        quota = DailyMessageQuota.get_quota(conversation, sender)
        
        # Check if free messages are available
        if quota.has_free_messages_remaining():
            return 0
        
        # After free limit, each message costs coins
        return settings.MESSAGE_COIN_COST
    
    @staticmethod
    @transaction.atomic
    def send_message(sender, receiver, content):
        """
        Send a message from sender to receiver with coin validation.
        
        This is the main business logic method for sending messages.
        Uses database transaction to ensure data consistency.
        
        Args:
            sender: User object sending the message
            receiver: User object receiving the message
            content: str - Message content
        
        Returns:
            Message: The created message object
        
        Raises:
            ValidationError: If message cannot be sent
            PermissionDenied: If sender lacks permission or coins
        """
        # Step 1: Validate permission to send
        can_send, reason = MessageService.can_send_message(sender, receiver)
        if not can_send:
            raise PermissionDenied(reason)
        
        # Step 2: Validate message content
        if not content or not content.strip():
            raise ValidationError("Message content cannot be empty")
        
        if len(content) > 1000:
            raise ValidationError("Message content too long (max 1000 characters)")
        
        # Step 3: Get or create conversation
        conversation, _ = Conversation.get_or_create_conversation(sender, receiver)
        
        # Step 4: Calculate coin cost
        coin_cost = MessageService.calculate_message_cost(sender, conversation)
        
        # Step 5: Handle coin deduction if needed
        coin_transaction = None
        if coin_cost > 0:
            try:
                # Get sender's wallet with row-level lock
                wallet = CoinWallet.objects.select_for_update().get(user=sender)
                
                # Deduct coins (this will raise ValidationError if insufficient balance)
                coin_transaction = wallet.deduct_coins(
                    amount=coin_cost,
                    transaction_type='message',
                    description=f'Message to {receiver.username}'
                )
                
                logger.info(
                    f"Deducted {coin_cost} coins from {sender.username} "
                    f"for message to {receiver.username}"
                )
                
            except CoinWallet.DoesNotExist:
                # Create wallet if it doesn't exist (shouldn't happen normally)
                wallet = CoinWallet.objects.create(user=sender)
                if wallet.balance < coin_cost:
                    raise ValidationError(
                        f"Insufficient coins. You need {coin_cost} coin(s) to send this message."
                    )
                coin_transaction = wallet.deduct_coins(
                    amount=coin_cost,
                    transaction_type='message',
                    description=f'Message to {receiver.username}'
                )
            
            except ValidationError as e:
                # Re-raise validation error with user-friendly message
                raise ValidationError(
                    f"Insufficient coins. You need {coin_cost} coin(s) to send this message. "
                    f"You have {wallet.balance} coin(s) remaining."
                )
        
        # Step 6: Create the message
        message = Message.objects.create(
            conversation=conversation,
            sender=sender,
            receiver=receiver,
            content=content.strip(),
            coin_cost=coin_cost
        )
        
        # Step 7: Link transaction to message if coins were spent
        if coin_transaction:
            coin_transaction.related_message = message
            coin_transaction.save(update_fields=['related_message'])
        
        # Step 8: Update daily quota
        quota = DailyMessageQuota.get_quota(conversation, sender)
        quota.increment(is_paid=(coin_cost > 0))
        
        # Step 9: Invalidate relevant caches
        MessageService._invalidate_message_caches(sender, receiver, conversation)
        
        # Step 10: Log the message
        logger.info(
            f"Message sent: {sender.username} -> {receiver.username}, "
            f"cost: {coin_cost} coins, conversation: {conversation.uuid}"
        )
        
        return message
    
    @staticmethod
    def _invalidate_message_caches(sender, receiver, conversation):
        """
        Invalidate relevant cache keys after sending a message.
        
        This ensures users see updated data without stale cache.
        """
        cache_keys = [
            f'conversation_messages_{conversation.id}',
            f'user_conversations_{sender.id}',
            f'user_conversations_{receiver.id}',
            f'unread_count_{receiver.id}',
            f'daily_quota_{conversation.id}_{sender.id}',
        ]
        
        cache.delete_many(cache_keys)
    
    @staticmethod
    def get_conversation_messages(conversation, page=1, per_page=50):
        """
        Get paginated messages for a conversation.
        
        Uses caching for performance.
        
        Args:
            conversation: Conversation object
            page: Page number (1-indexed)
            per_page: Messages per page
        
        Returns:
            QuerySet: Message objects with related data pre-fetched
        """
        cache_key = f'conversation_messages_{conversation.id}_page_{page}'
        cached_messages = cache.get(cache_key)
        
        if cached_messages is not None:
            return cached_messages
        
        # Calculate offset
        offset = (page - 1) * per_page
        
        # Fetch messages with optimized query
        messages = Message.objects.filter(
            conversation=conversation
        ).select_related(
            'sender__profile',
            'receiver__profile'
        ).order_by('created_at')[offset:offset + per_page]
        
        # Cache for 2 minutes (messages are relatively static once sent)
        cache.set(cache_key, messages, 120)
        
        return messages
    
    @staticmethod
    def get_user_conversations(user, limit=20):
        """
        Get user's conversations ordered by most recent message.
        
        Optimized with select_related and prefetch_related.
        Cached for performance.
        
        Args:
            user: User object
            limit: Maximum number of conversations to return
        
        Returns:
            QuerySet: Conversation objects with related data
        """
        cache_key = f'user_conversations_{user.id}_limit_{limit}'
        cached_conversations = cache.get(cache_key)
        
        if cached_conversations is not None:
            return cached_conversations
        
        # Get conversations where user is a participant
        from django.db.models import Q, Prefetch
        
        conversations = Conversation.objects.filter(
            Q(participant_1=user) | Q(participant_2=user)
        ).select_related(
            'participant_1__profile',
            'participant_2__profile'
        ).prefetch_related(
            Prefetch(
                'messages',
                queryset=Message.objects.order_by('-created_at')[:1],
                to_attr='latest_message'
            )
        ).order_by('-last_message_at')[:limit]
        
        # Cache for 1 minute
        cache.set(cache_key, conversations, 60)
        
        return conversations
    
    @staticmethod
    def get_unread_message_count(user):
        """
        Get count of unread messages for a user.
        
        Cached aggressively since this is checked frequently.
        
        Args:
            user: User object
        
        Returns:
            int: Count of unread messages
        """
        cache_key = f'unread_count_{user.id}'
        cached_count = cache.get(cache_key)
        
        if cached_count is not None:
            return cached_count
        
        count = Message.objects.filter(
            receiver=user,
            is_read=False
        ).count()
        
        # Cache for 30 seconds
        cache.set(cache_key, count, 30)
        
        return count
    
    @staticmethod
    def mark_conversation_as_read(conversation, user):
        """
        Mark all messages in a conversation as read for the given user.
        
        Args:
            conversation: Conversation object
            user: User who is reading the messages
        
        Returns:
            int: Number of messages marked as read
        """
        updated_count = Message.objects.filter(
            conversation=conversation,
            receiver=user,
            is_read=False
        ).update(
            is_read=True,
            read_at=timezone.now()
        )
        
        # Invalidate unread count cache
        cache.delete(f'unread_count_{user.id}')
        
        logger.info(
            f"Marked {updated_count} messages as read for {user.username} "
            f"in conversation {conversation.uuid}"
        )
        
        return updated_count


# ============================================================================
# COIN SERVICE
# ============================================================================

class CoinService:
    """
    Encapsulates business logic for coin operations.
    """
    
    @staticmethod
    @transaction.atomic
    def purchase_coins(user, amount, payment_reference=''):
        """
        Process a coin purchase.
        
        In production, this would integrate with payment gateway.
        
        Args:
            user: User purchasing coins
            amount: Number of coins to purchase
            payment_reference: External payment reference ID
        
        Returns:
            CoinTransaction: The transaction record
        """
        # Get or create wallet
        wallet, created = CoinWallet.objects.get_or_create(user=user)
        
        # Add coins
        transaction_obj = wallet.add_coins(
            amount=amount,
            transaction_type='purchase',
            description=f'Purchased {amount} coins. Ref: {payment_reference}'
        )
        
        # Update purchase statistics
        wallet.total_purchased += amount
        wallet.save(update_fields=['total_purchased'])
        
        logger.info(
            f"User {user.username} purchased {amount} coins. "
            f"New balance: {wallet.balance}"
        )
        
        return transaction_obj
    
    @staticmethod
    @transaction.atomic
    def award_coins(user, amount, reason=''):
        """
        Award free coins to user (rewards, bonuses, etc.).
        
        Args:
            user: User receiving coins
            amount: Number of coins to award
            reason: Why coins are being awarded
        
        Returns:
            CoinTransaction: The transaction record
        """
        wallet, created = CoinWallet.objects.get_or_create(user=user)
        
        transaction_obj = wallet.add_coins(
            amount=amount,
            transaction_type='reward',
            description=reason or f'Rewarded {amount} coins'
        )
        
        logger.info(
            f"Awarded {amount} coins to {user.username}. "
            f"Reason: {reason}. New balance: {wallet.balance}"
        )
        
        return transaction_obj
    
    @staticmethod
    def get_transaction_history(user, limit=50):
        """
        Get coin transaction history for a user.
        
        Args:
            user: User object
            limit: Maximum number of transactions to return
        
        Returns:
            QuerySet: CoinTransaction objects
        """
        try:
            wallet = CoinWallet.objects.get(user=user)
            return wallet.transactions.all()[:limit]
        except CoinWallet.DoesNotExist:
            return CoinTransaction.objects.none()
    
    @staticmethod
    def get_wallet_balance(user):
        """
        Get user's current coin balance.
        
        Cached for performance.
        
        Args:
            user: User object
        
        Returns:
            int: Current coin balance
        """
        cache_key = f'coin_balance_{user.id}'
        cached_balance = cache.get(cache_key)
        
        if cached_balance is not None:
            return cached_balance
        
        try:
            wallet = CoinWallet.objects.get(user=user)
            balance = wallet.balance
        except CoinWallet.DoesNotExist:
            balance = 0
        
        # Cache for 1 minute
        cache.set(cache_key, balance, 60)
        
        return balance