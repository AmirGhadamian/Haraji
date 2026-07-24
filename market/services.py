"""
لایه منطق کسب‌وکار مربوط به ودیعه، ثبت پیشنهاد امن، و پرداخت نهایی.
همه‌ی این توابع باید از views (نه مستقیم از تمپلیت یا جای دیگر) صدا زده شوند.
"""
from django.db import transaction
from django.utils import timezone

from .models import Auction, Bid, Deposit, Order


class AuctionError(Exception):
    """خطای قابل‌نمایش به کاربر (پیام‌های مربوط به قوانین حراجی)"""
    pass


# ---------------------------------------------------------------------------
# ودیعه
# ---------------------------------------------------------------------------

def create_deposit_payment_request(auction: Auction, user):
    if Deposit.objects.filter(auction=auction, user=user, status=Deposit.STATUS_PAID).exists():
        raise AuctionError('شما قبلاً ودیعه این حراجی را پرداخت کرده‌اید.')

    return Deposit.objects.create(
        auction=auction,
        user=user,
        amount=auction.deposit_amount,
        status=Deposit.STATUS_PENDING,
    )


def confirm_deposit_payment(deposit: Deposit, gateway_ref: str):
    with transaction.atomic():
        deposit.refresh_from_db()
        if deposit.status == Deposit.STATUS_PAID:
            return deposit  # جلوگیری از پردازش دوباره callback تکراری درگاه
        deposit.status = Deposit.STATUS_PAID
        deposit.payment_gateway_ref = gateway_ref
        deposit.save(update_fields=['status', 'payment_gateway_ref'])
    return deposit


def user_has_active_deposit(auction: Auction, user) -> bool:
    if not user.is_authenticated:
        return False
    return Deposit.objects.filter(auction=auction, user=user, status=Deposit.STATUS_PAID).exists()


# ---------------------------------------------------------------------------
# ثبت پیشنهاد امن (جلوگیری از race condition بین دو پیشنهاد همزمان)
# ---------------------------------------------------------------------------

@transaction.atomic
def place_bid(auction_id: int, user, amount) -> Bid:
    auction = Auction.objects.select_for_update().get(pk=auction_id)

    if auction.is_closed or auction.is_finished_by_time:
        raise AuctionError('این حراجی به پایان رسیده است.')

    if auction.listing.seller_id == user.id:
        raise AuctionError('فروشنده نمی‌تواند در حراجی خودش شرکت کند.')

    if not user_has_active_deposit(auction, user):
        raise AuctionError('برای ثبت پیشنهاد ابتدا باید ودیعه حراجی را پرداخت کنید.')

    min_required = auction.minimum_next_bid()
    if amount < min_required:
        raise AuctionError(f'مبلغ پیشنهادی باید حداقل {int(min_required)} تومان باشد.')

    return Bid.objects.create(auction=auction, bidder=user, amount=amount)


# ---------------------------------------------------------------------------
# مدیریت عدم پرداخت برنده (جریمه ودیعه)
# ---------------------------------------------------------------------------

@transaction.atomic
def expire_unpaid_order(order_id: int):
    order = Order.objects.select_for_update().get(pk=order_id)

    if order.status != Order.STATUS_PENDING or timezone.now() < order.payment_deadline:
        return order

    order.status = Order.STATUS_EXPIRED
    order.save(update_fields=['status'])

    winner_deposit = Deposit.objects.filter(
        auction=order.auction, user=order.buyer, status=Deposit.STATUS_APPLIED
    ).first()
    if winner_deposit:
        winner_deposit.status = Deposit.STATUS_FORFEITED
        winner_deposit.save(update_fields=['status'])

    return order


@transaction.atomic
def confirm_order_payment(order: Order, gateway_ref: str):
    order.refresh_from_db()
    if order.status == Order.STATUS_PAID:
        return order
    order.status = Order.STATUS_PAID
    order.payment_gateway_ref = gateway_ref
    order.paid_at = timezone.now()
    order.save(update_fields=['status', 'payment_gateway_ref', 'paid_at'])
    # TODO: اینجا واریز مبلغ hammer_price به حساب فروشنده را صدا بزنید
    return order
