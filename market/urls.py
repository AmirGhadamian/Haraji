from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('register/', views.register, name='register'),
    path('my-account/', views.my_listings, name='my_listings'),

    path('listings/new/', views.create_listing, name='create_listing'),
    path('listings/<int:pk>/', views.listing_detail, name='listing_detail'),
    path('listings/<int:pk>/start-auction/', views.start_auction, name='start_auction'),

    path('auctions/', views.auction_list, name='auction_list'),
    path('auctions/<int:pk>/', views.auction_detail, name='auction_detail'),
    path('auctions/<int:pk>/pay-deposit/', views.pay_deposit, name='pay_deposit'),
    path('orders/<int:pk>/pay/', views.pay_order, name='pay_order'),
]
