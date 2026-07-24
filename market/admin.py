from django.contrib import admin
from .models import Category, Listing, Auction, Bid, Deposit, Order


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name']


@admin.register(Listing)
class ListingAdmin(admin.ModelAdmin):
    list_display = ['title', 'seller', 'category', 'price', 'status', 'created_at']
    list_filter = ['status', 'category']
    search_fields = ['title', 'description']


@admin.register(Auction)
class AuctionAdmin(admin.ModelAdmin):
    list_display = ['listing', 'starting_price', 'end_time', 'is_closed', 'winner']
    list_filter = ['is_closed']


@admin.register(Bid)
class BidAdmin(admin.ModelAdmin):
    list_display = ['auction', 'bidder', 'amount', 'created_at']


@admin.register(Deposit)
class DepositAdmin(admin.ModelAdmin):
    list_display = ['auction', 'user', 'amount', 'status', 'created_at']
    list_filter = ['status']


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['auction', 'buyer', 'total_payable', 'status', 'payment_deadline']
    list_filter = ['status']
