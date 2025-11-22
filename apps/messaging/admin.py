from django.contrib import admin
from .models import CoinWallet, CoinTransaction, Conversation, Message, DailyMessageQuota


# Register your models here.
admin.site.register(CoinWallet)
admin.site.register(CoinTransaction)
admin.site.register(Conversation)
admin.site.register(Message)
admin.site.register(DailyMessageQuota)


