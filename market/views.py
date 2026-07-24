from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import render, redirect, get_object_or_404

from .forms import RegisterForm, ListingForm, AuctionForm, BidForm
from .models import Category, Listing, Auction, Bid, Deposit, Order
from .services import (
    AuctionError,
    confirm_deposit_payment,
    confirm_order_payment,
    create_deposit_payment_request,
    place_bid,
    user_has_active_deposit,
)


def _close_expired_auctions():
    """هر بار قبل از نمایش صفحات حراجی، حراجی‌های تمام‌شده را می‌بندیم."""
    for auction in Auction.objects.filter(is_closed=False):
        auction.close_if_needed()


def home(request):
    _close_expired_auctions()
    category_id = request.GET.get('category')
    q = request.GET.get('q', '').strip()

    listings = Listing.objects.exclude(status=Listing.STATUS_SOLD)
    if category_id:
        listings = listings.filter(category_id=category_id)
    if q:
        listings = listings.filter(title__icontains=q)

    paginator = Paginator(listings, 12)
    page_obj = paginator.get_page(request.GET.get('page'))

    active_auctions = Auction.objects.filter(is_closed=False).order_by('end_time')[:6]

    return render(request, 'market/home.html', {
        'page_obj': page_obj,
        'categories': Category.objects.all(),
        'active_auctions': active_auctions,
        'selected_category': category_id,
        'q': q,
    })


def listing_detail(request, pk):
    listing = get_object_or_404(Listing, pk=pk)
    if hasattr(listing, 'auction'):
        listing.auction.close_if_needed()
    return render(request, 'market/listing_detail.html', {'listing': listing})


@login_required
def create_listing(request):
    if request.method == 'POST':
        form = ListingForm(request.POST, request.FILES)
        if form.is_valid():
            listing = form.save(commit=False)
            listing.seller = request.user
            listing.save()
            messages.success(request, 'آگهی شما با موفقیت ثبت شد.')
            return redirect('listing_detail', pk=listing.pk)
    else:
        form = ListingForm()
    return render(request, 'market/listing_form.html', {'form': form})


@login_required
def start_auction(request, pk):
    listing = get_object_or_404(Listing, pk=pk, seller=request.user)
    if hasattr(listing, 'auction'):
        messages.warning(request, 'این آگهی قبلاً وارد حراجی شده است.')
        return redirect('listing_detail', pk=listing.pk)

    if request.method == 'POST':
        form = AuctionForm(request.POST)
        if form.is_valid():
            auction = form.save(commit=False)
            auction.listing = listing
            auction.save()
            listing.status = Listing.STATUS_AUCTION
            listing.save()
            messages.success(request, 'آگهی شما با موفقیت وارد حراجی شد.')
            return redirect('auction_detail', pk=auction.pk)
    else:
        form = AuctionForm(initial={'starting_price': listing.price})
    return render(request, 'market/auction_form.html', {'form': form, 'listing': listing})


def auction_list(request):
    _close_expired_auctions()
    auctions = Auction.objects.filter(is_closed=False).order_by('end_time')
    paginator = Paginator(auctions, 12)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'market/auction_list.html', {'page_obj': page_obj})


def auction_detail(request, pk):
    auction = get_object_or_404(Auction, pk=pk)
    auction.close_if_needed()

    has_deposit = user_has_active_deposit(auction, request.user)
    can_bid = (
        request.user.is_authenticated
        and auction.is_active
        and auction.listing.seller != request.user
    )

    bid_form = None
    if can_bid and has_deposit:
        if request.method == 'POST':
            bid_form = BidForm(request.POST, auction=auction)
            if bid_form.is_valid():
                try:
                    place_bid(auction.pk, request.user, bid_form.cleaned_data['amount'])
                    messages.success(request, 'پیشنهاد قیمت شما ثبت شد.')
                    return redirect('auction_detail', pk=auction.pk)
                except AuctionError as e:
                    bid_form.add_error(None, str(e))
        else:
            bid_form = BidForm(auction=auction)

    my_order = None
    if auction.is_closed and auction.winner_id == getattr(request.user, 'id', None):
        my_order = getattr(auction, 'order', None)

    bids = auction.bids.select_related('bidder').order_by('-amount', 'created_at')
    return render(request, 'market/auction_detail.html', {
        'auction': auction,
        'bid_form': bid_form,
        'bids': bids,
        'can_bid': can_bid,
        'has_deposit': has_deposit,
        'my_order': my_order,
    })


@login_required
def pay_deposit(request, pk):
    auction = get_object_or_404(Auction, pk=pk)
    try:
        deposit = create_deposit_payment_request(auction, request.user)
    except AuctionError as e:
        messages.error(request, str(e))
        return redirect('auction_detail', pk=auction.pk)

    # TODO: اینجا کاربر باید به درگاه واقعی (زرین‌پال/آیدی‌پی) هدایت شود
    # فعلاً برای تست بدون درگاه، مستقیم تایید می‌کنیم:
    confirm_deposit_payment(deposit, gateway_ref='TEST-REF')
    messages.success(request, f'ودیعه {int(deposit.amount)} تومانی با موفقیت پرداخت شد.')
    return redirect('auction_detail', pk=auction.pk)


@login_required
def pay_order(request, pk):
    order = get_object_or_404(Order, pk=pk, buyer=request.user)
    if order.status != Order.STATUS_PENDING:
        messages.warning(request, 'این سفارش قابل پرداخت نیست.')
        return redirect('auction_detail', pk=order.auction_id)

    # TODO: اینجا کاربر باید به درگاه واقعی هدایت شود
    confirm_order_payment(order, gateway_ref='TEST-REF')
    messages.success(request, 'پرداخت نهایی با موفقیت انجام شد.')
    return redirect('auction_detail', pk=order.auction_id)


def register(request):
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, 'ثبت‌نام با موفقیت انجام شد. خوش آمدید!')
            return redirect('home')
    else:
        form = RegisterForm()
    return render(request, 'registration/register.html', {'form': form})


@login_required
def my_listings(request):
    listings = Listing.objects.filter(seller=request.user)
    my_bids = Bid.objects.filter(bidder=request.user).select_related('auction', 'auction__listing')
    won = Auction.objects.filter(winner=request.user)
    return render(request, 'market/my_listings.html', {
        'listings': listings,
        'my_bids': my_bids,
        'won': won,
    })
