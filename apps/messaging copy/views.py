# ============================================================================
# MESSAGING VIEWS
# ============================================================================

"""
apps/messaging/views.py
"""

from django.conf import settings
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError, PermissionDenied
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page

from apps.common import models


from .models import DailyMessageQuota, Message, Conversation, CoinWallet
from .serializers import (
    MessageSerializer, MessageCreateSerializer,
    ConversationSerializer, CoinWalletSerializer,
    CoinTransactionSerializer
)
from .services import MessageService, CoinService
from apps.common.pagination import StandardResultsSetPagination

User = get_user_model()


class ConversationViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for managing conversations.
    
    Demonstrates:
    - Read-only viewset (list and retrieve only)
    - Custom actions with @action decorator
    - Service layer integration
    - Caching with method_decorator
    """
    
    serializer_class = ConversationSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    lookup_field = 'uuid'
    
    def get_queryset(self):
        """
        Get conversations for current user.
        Uses service layer for optimized query.
        """
        return MessageService.get_user_conversations(
            user=self.request.user,
            limit=100
        )
    
    @action(detail=True, methods=['get'])
    def messages(self, request, uuid=None):
        """
        Get messages for a specific conversation.
        
        GET /api/conversations/{uuid}/messages/
        
        Query params:
        - page: Page number for pagination
        """
        conversation = self.get_object()
        
        # Get messages using service
        page = request.query_params.get('page', 1)
        messages = MessageService.get_conversation_messages(
            conversation=conversation,
            page=int(page),
            per_page=50
        )
        
        # Paginate results
        paginator = StandardResultsSetPagination()
        paginated_messages = paginator.paginate_queryset(messages, request)
        
        serializer = MessageSerializer(
            paginated_messages,
            many=True,
            context={'request': request}
        )
        
        return paginator.get_paginated_response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def mark_read(self, request, uuid=None):
        """
        Mark all messages in conversation as read.
        
        POST /api/conversations/{uuid}/mark_read/
        """
        conversation = self.get_object()
        
        # Mark messages as read using service
        count = MessageService.mark_conversation_as_read(
            conversation=conversation,
            user=request.user
        )
        
        return Response({
            'message': f'Marked {count} messages as read',
            'count': count
        }, status=status.HTTP_200_OK)
    
    @action(detail=False, methods=['get'])
    def unread_count(self, request):
        """
        Get total unread message count for current user.
        
        GET /api/conversations/unread_count/
        """
        count = MessageService.get_unread_message_count(request.user)
        
        return Response({
            'unread_count': count
        }, status=status.HTTP_200_OK)


class MessageViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing messages.
    
    Demonstrates:
    - Full CRUD operations (though we only allow create and read)
    - Service layer for business logic
    - Error handling
    - Custom permissions
    """
    
    serializer_class = MessageSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    lookup_field = 'uuid'
    
    def get_queryset(self):
        """
        Get messages for current user.
        Either sent or received.
        """
        return Message.objects.filter(
            models.Q(sender=self.request.user) | 
            models.Q(receiver=self.request.user)
        ).select_related(
            'sender__profile',
            'receiver__profile',
            'conversation'
        ).order_by('-created_at')
    
    def get_serializer_class(self):
        """
        Use different serializers for different actions.
        """
        if self.action == 'create':
            return MessageCreateSerializer
        return MessageSerializer
    
    def create(self, request, *args, **kwargs):
        """
        Send a new message.
        
        POST /api/messages/
        Body: {
            "receiver_uuid": "uuid-of-receiver",
            "content": "message content"
        }
        
        Response includes:
        - Message data
        - Coin cost
        - Whether it was free or paid
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Get receiver
        receiver_uuid = serializer.validated_data['receiver_uuid']
        try:
            receiver = User.objects.get(uuid=receiver_uuid)
        except (User.DoesNotExist, ValidationError):
            return Response({
                'error': 'Receiver not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Send message using service
        try:
            message = MessageService.send_message(
                sender=request.user,
                receiver=receiver,
                content=serializer.validated_data['content']
            )
            
            # Serialize response
            response_serializer = MessageSerializer(
                message,
                context={'request': request}
            )
            
            return Response({
                'message': 'Message sent successfully',
                'data': response_serializer.data,
                'coin_cost': message.coin_cost,
                'was_free': message.coin_cost == 0
            }, status=status.HTTP_201_CREATED)
            
        except ValidationError as e:
            return Response({
                'error': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)
            
        except PermissionDenied as e:
            return Response({
                'error': str(e)
            }, status=status.HTTP_403_FORBIDDEN)
    
    @action(detail=False, methods=['get'])
    def check_cost(self, request):
        """
        Check the coin cost for sending a message to a user.
        
        GET /api/messages/check_cost/?receiver_uuid=xxx
        
        Useful for frontend to show cost before sending.
        """
        receiver_uuid = request.query_params.get('receiver_uuid')
        
        if not receiver_uuid or receiver_uuid == 'undefined':
            return Response({
                'error': 'A valid receiver_uuid is required.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            receiver = User.objects.get(uuid=receiver_uuid)
        except (User.DoesNotExist, ValidationError):
            return Response({
                'error': 'Receiver not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Get or create conversation
        conversation, _ = Conversation.get_or_create_conversation(
            request.user, receiver
        )
        
        # Calculate cost
        cost = MessageService.calculate_message_cost(
            request.user, conversation
        )
        
        # Get remaining free messages
        quota = DailyMessageQuota.get_quota(conversation, request.user)
        free_remaining = max(0, settings.FREE_MESSAGES_LIMIT - quota.free_messages_used)
        
        return Response({
            'coin_cost': cost,
            'is_free': cost == 0,
            'free_messages_remaining': free_remaining,
            'free_messages_limit': settings.FREE_MESSAGES_LIMIT
        }, status=status.HTTP_200_OK)


class CoinWalletViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for coin wallet operations.
    
    Read-only for viewing balance and transactions.
    Purchases handled through separate payment endpoints.
    """
    
    serializer_class = CoinWalletSerializer
    permission_classes = [IsAuthenticated]
    
    def get_object(self):
        """
        Get current user's wallet.
        """
        wallet, _ = CoinWallet.objects.get_or_create(user=self.request.user)
        return wallet
    
    def list(self, request, *args, **kwargs):
        """
        GET /api/wallet/
        
        Returns current user's wallet information.
        """
        wallet = self.get_object()
        serializer = self.get_serializer(wallet)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def transactions(self, request):
        """
        Get transaction history.
        
        GET /api/wallet/transactions/
        """
        transactions = CoinService.get_transaction_history(
            user=request.user,
            limit=100
        )
        
        paginator = StandardResultsSetPagination()
        paginated_transactions = paginator.paginate_queryset(transactions, request)
        
        serializer = CoinTransactionSerializer(
            paginated_transactions,
            many=True
        )
        
        return paginator.get_paginated_response(serializer.data)
    
    @action(detail=False, methods=['post'])
    def purchase(self, request):
        """
        Purchase coins.
        
        POST /api/wallet/purchase/
        Body: {
            "amount": 100,
            "payment_reference": "stripe_payment_id"
        }
        
        Note: In production, integrate with payment gateway.
        This is simplified version.
        """
        amount = request.data.get('amount')
        payment_reference = request.data.get('payment_reference', '')
        
        if not amount or amount <= 0:
            return Response({
                'error': 'Invalid amount'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Process purchase using service
        transaction = CoinService.purchase_coins(
            user=request.user,
            amount=amount,
            payment_reference=payment_reference
        )
        
        serializer = CoinTransactionSerializer(transaction)
        
        return Response({
            'message': f'Successfully purchased {amount} coins',
            'transaction': serializer.data
        }, status=status.HTTP_200_OK)