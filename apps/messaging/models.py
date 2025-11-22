"""
Messaging and Coin System Models
==================================
Demonstrates:
- Token/Coin-based messaging monetization
- Transaction tracking for audit trail
- Efficient conversation grouping
- Custom managers for complex queries
- Business rule enforcement at model level

Business Rules:
- Users get 3 free messages per conversation per day
- After 3 messages, each message costs 1 coin
- Coins are purchased or earned through app activities
"""

from django.db import models, transaction
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import timedelta, date
import uuid


# ============================================================================
# COIN WALLET MODEL
# ============================================================================

class CoinWallet(models.Model):
    """
    Each user has a coin wallet for purchasing message access.
    
    Design Pattern: Separate wallet model for:
    - Easy transaction tracking
    - Potential future expansion (multiple currencies)
    - Audit trail
    """
    
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='coin_wallet',
        primary_key=True
    )
    
    balance = models.PositiveIntegerField(
        default=10,  # Give new users 10 coins to start
        help_text=_('Current coin balance')
    )
    
    # Lifetime statistics
    total_earned = models.PositiveIntegerField(
        default=10,
        help_text=_('Total coins earned (including initial)')
    )
    
    total_spent = models.PositiveIntegerField(
        default=0,
        help_text=_('Total coins spent')
    )
    
    total_purchased = models.PositiveIntegerField(
        default=0,
        help_text=_('Total coins purchased with real money')
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'coin_wallets'
    
    def __str__(self):
        return f"{self.user.username}'s wallet: {self.balance} coins"
    
    def has_sufficient_balance(self, amount):
        """
        Check if user has enough coins.
        """
        return self.balance >= amount
    
    def add_coins(self, amount, transaction_type, description=''):
        """
        Add coins to wallet with transaction record.
        
        Args:
            amount: Number of coins to add
            transaction_type: Type of transaction (see CoinTransaction.TRANSACTION_TYPES)
            description: Optional description
        
        Returns:
            CoinTransaction object
        """
        with transaction.atomic():
            # Lock the wallet row to prevent race conditions
            wallet = CoinWallet.objects.select_for_update().get(pk=self.pk)
            wallet.balance += amount
            wallet.total_earned += amount
            wallet.save(update_fields=['balance', 'total_earned', 'updated_at'])
            
            # Create transaction record
            coin_transaction = CoinTransaction.objects.create(
                wallet=wallet,
                amount=amount,
                transaction_type=transaction_type,
                balance_after=wallet.balance,
                description=description
            )
            
            self.refresh_from_db()
            return coin_transaction
    
    def deduct_coins(self, amount, transaction_type, description=''):
        """
        Deduct coins from wallet with transaction record.
        Raises ValidationError if insufficient balance.
        
        Args:
            amount: Number of coins to deduct
            transaction_type: Type of transaction
            description: Optional description
        
        Returns:
            CoinTransaction object
        
        Raises:
            ValidationError: If insufficient balance
        """
        if not self.has_sufficient_balance(amount):
            raise ValidationError(
                _('Insufficient coin balance. You need %(amount)s coins.'),
                params={'amount': amount}
            )
        
        with transaction.atomic():
            # Lock the wallet row to prevent race conditions
            wallet = CoinWallet.objects.select_for_update().get(pk=self.pk)
            wallet.balance -= amount
            wallet.total_spent += amount
            wallet.save(update_fields=['balance', 'total_spent', 'updated_at'])
            
            # Create transaction record (negative amount for deduction)
            coin_transaction = CoinTransaction.objects.create(
                wallet=wallet,
                amount=-amount,
                transaction_type=transaction_type,
                balance_after=wallet.balance,
                description=description
            )
            
            self.refresh_from_db()
            return coin_transaction
        
# ============================================================================
# COIN TRANSACTION MODEL
# ============================================================================

class CoinTransaction(models.Model):
    """
    Immutable record of all coin transactions.
    Provides audit trail and history.
    """
    
    TRANSACTION_TYPES = [
        ('purchase', 'Purchased with Money'),
        ('message', 'Spent on Message'),
        ('reward', 'Earned as Reward'),
        ('bonus', 'Bonus Coins'),
        ('refund', 'Refund'),
        ('admin', 'Admin Adjustment'),
    ]
    
    uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        db_index=True
    )
    
    wallet = models.ForeignKey(
        CoinWallet,
        on_delete=models.CASCADE,
        related_name='transactions'
    )
    
    amount = models.IntegerField(
        help_text=_('Positive for credit, negative for debit')
    )
    
    transaction_type = models.CharField(
        max_length=20,
        choices=TRANSACTION_TYPES,
        db_index=True
    )
    
    balance_after = models.PositiveIntegerField(
        help_text=_('Balance after this transaction')
    )
    
    description = models.CharField(
        max_length=255,
        blank=True
    )
    
    # Link to related message if transaction is for messaging
    related_message = models.ForeignKey(
        'Message',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='coin_transactions'
    )
    
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        db_table = 'coin_transactions'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['wallet', '-created_at']),
            models.Index(fields=['transaction_type', '-created_at']),
        ]
    
    def __str__(self):
        sign = '+' if self.amount > 0 else ''
        return f"{self.wallet.user.username}: {sign}{self.amount} coins ({self.transaction_type})"
    
# ============================================================================
# CONVERSATION MODEL
# ============================================================================

class Conversation(models.Model):
    """
    Groups messages between two users.
    
    Design Pattern: Explicit conversation model rather than inferring from messages.
    Benefits:
    - Faster queries (don't need to scan all messages)
    - Can store conversation-level metadata
    - Easier to implement features like muting, archiving
    """
    
    uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        db_index=True
    )
    
    # The two participants (always sorted to ensure uniqueness)
    participant_1 = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='conversations_as_participant_1'
    )
    
    participant_2 = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='conversations_as_participant_2'
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    last_message_at = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        db_table = 'conversations'
        unique_together = ['participant_1', 'participant_2']
        indexes = [
            models.Index(fields=['participant_1', '-last_message_at']),
            models.Index(fields=['participant_2', '-last_message_at']),
        ]
        ordering = ['-last_message_at']
    
    def __str__(self):
        return f"Conversation: {self.participant_1.username} <-> {self.participant_2.username}"
    
    def save(self, *args, **kwargs):
        """
        Override save to ensure participants are always ordered.
        This prevents duplicate conversations with reversed participants.
        """
        if self.participant_1_id > self.participant_2_id:
            self.participant_1, self.participant_2 = self.participant_2, self.participant_1
        
        super().save(*args, **kwargs)
    
    def get_other_participant(self, user):
        """
        Get the other participant in conversation for given user.
        """
        if user == self.participant_1:
            return self.participant_2
        return self.participant_1
    
    def get_message_count_today(self, sender):
        """
        Get count of messages sent by sender today.
        Used to determine if coins are needed.
        """
        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        return self.messages.filter(
            sender=sender,
            created_at__gte=today_start
        ).count()
    
    def requires_coins(self, sender):
        """
        Check if sender needs to spend coins to send a message.
        
        Business Rule:
        - First 3 messages per day are free
        - Subsequent messages cost coins
        """
        message_count_today = self.get_message_count_today(sender)
        return message_count_today >= settings.FREE_MESSAGES_LIMIT
    
    @classmethod
    def get_or_create_conversation(cls, user1, user2):
        """
        Get existing conversation or create new one between two users.
        Handles participant ordering automatically.
        """
        # Ensure consistent ordering
        if user1.id > user2.id:
            user1, user2 = user2, user1
        
        conversation, created = cls.objects.get_or_create(
            participant_1=user1,
            participant_2=user2
        )
        
        return conversation, created

class Message(models.Model):
    """
    Individual messages within a conversation.
    
    Design Decisions:
    - Store conversation FK for efficient querying
    - Store both sender and receiver explicitly for clarity
    - Track coin_cost to show in message history
    """
    
    uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        db_index=True
    )
    
    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name='messages'
    )
    
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='sent_messages'
    )
    
    receiver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='received_messages'
    )
    
    content = models.TextField(
        max_length=1000,
        help_text=_('Message content (max 1000 characters)')
    )
    
    # Coin tracking
    coin_cost = models.PositiveIntegerField(
        default=0,
        help_text=_('Number of coins spent to send this message')
    )
    
    # Message status
    is_read = models.BooleanField(default=False, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        db_table = 'messages'
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['conversation', 'created_at']),
            models.Index(fields=['sender', '-created_at']),
            models.Index(fields=['receiver', 'is_read']),
        ]
    
    def __str__(self):
        return f"Message from {self.sender.username} to {self.receiver.username}"
    
    def mark_as_read(self):
        """
        Mark message as read and record timestamp.
        """
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=['is_read', 'read_at'])
    
    def save(self, *args, **kwargs):
        """
        Override save to update conversation's last_message_at.
        """
        super().save(*args, **kwargs)
        
        # Update conversation timestamp
        self.conversation.last_message_at = self.created_at
        self.conversation.save(update_fields=['last_message_at'])

# ============================================================================
# DAILY MESSAGE QUOTA TRACKING
# ============================================================================

class DailyMessageQuota(models.Model):
    """
    Tracks daily message quotas PER USER (not per conversation).
    This ensures 3 free messages TOTAL per day, not per conversation.
    """
    
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='daily_quotas'
    )
    
    date = models.DateField(
        default=date.today,
        db_index=True
    )
    
    # Total messages sent today
    total_messages_sent = models.PositiveIntegerField(default=0)
    
    # Free messages used today (across ALL conversations)
    free_messages_used = models.PositiveIntegerField(default=0)
    
    # Paid messages sent today
    paid_messages_sent = models.PositiveIntegerField(default=0)
    
    class Meta:
        db_table = 'daily_message_quotas'
        unique_together = ['user', 'date']
        indexes = [
            models.Index(fields=['user', 'date']),
        ]
    
    def __str__(self):
        return f"{self.user.username} - {self.date}: {self.total_messages_sent} messages"
    
    @classmethod
    def get_quota(cls, user, date_obj=None):
        """
        Get or create quota for user for today.
        """
        if date_obj is None:
            date_obj = date.today()
        
        quota, created = cls.objects.get_or_create(
            user=user,
            date=date_obj,
            defaults={
                'total_messages_sent': 0,
                'free_messages_used': 0,
                'paid_messages_sent': 0
            }
        )
        
        return quota
    
    def increment(self, is_paid=False):
        """
        Increment message count.
        """
        self.total_messages_sent += 1
        if is_paid:
            self.paid_messages_sent += 1
        else:
            self.free_messages_used += 1
        self.save(update_fields=['total_messages_sent', 'free_messages_used', 'paid_messages_sent'])
    
    def has_free_messages_remaining(self):
        """
        Check if user still has free messages for today (GLOBALLY).
        """
        return self.free_messages_used < settings.FREE_MESSAGES_LIMIT
