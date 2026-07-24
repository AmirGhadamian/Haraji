from decimal import Decimal

from django.db import models
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone


class Category(models.Model):
    name = models.CharField('نام دسته', max_length=100)

    class Meta:
        verbose_name = 'دسته‌بندی'
        verbose_name_plural = 'دسته‌بندی‌ها'

    def __str__(self):
        return self.name


class Listing(models.Model):
    STATUS_NORMAL = 'normal'
    STATUS_AUCTION = 'auction'
    STATUS_SOLD = 'sold'
    STATUS_CHOICES = [
        (STATUS_NORMAL, 'آگهی عادی'),
        (STATUS_AUCTION, 'در حال حراجی'),
        (STATUS_SOLD, 'فروخته شده'),
    ]

    title = models.CharField('عنوان', max_length=200)
    description = models.TextField('توضیحات')
    price = models.DecimalField('قیمت (تومان)', max_digits=12, decimal_places=0)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True,
                                  related_name='listings', verbose_name='دسته‌بندی')
    seller = models.ForeignKey(User, on_delete=models.CASCADE, related_name='listings',
                                verbose_name='فروشنده')
    image = models.ImageField('تصویر', upload_to='listings/', blank=True, null=True)
    status = models.CharField('وضعیت', max_length=10, choices=STATUS_CHOICES, default=STATUS_NORMAL)
    created_at = models.DateTimeField('تاریخ ثبت', auto_now_add=True)

    class Meta:
        verbose_name = 'آگهی'
        verbose_name_plural = 'آگهی‌ها'
        ordering = ['-created_at']

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('listing_detail', args=[self.pk])

    @property
    def has_active_auction(self):
        return hasattr(self, 'auction') and self.auction.is_active


class Auction(models.Model):
    listing = models.OneToOneField(Listing, on_delete=models.CASCADE, related_name='auction',
                                    verbose_name='آگهی')
    starting_price = models.DecimalField('قیمت پایه', max_digits=12, decimal_places=0)
    min_increment = models.DecimalField('حداقل افزایش قیمت', max_digits=12, decimal_places=0, default=1000)
    start_time = models.DateTimeField('زمان شروع', default=timezone.now)
    end_time = models.DateTimeField('زمان پایان')
    is_closed = models.BooleanField('پایان‌یافته', default=False)
    winner = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='won_auctions', verbose_name='برنده')

    # --- کارمزد خریدار و ودیعه ---
    buyer_premium_percent = models.DecimalField('درصد کارمزد خریدار', max_digits=5, decimal_places=2,
                                                  default=10)
    deposit_amount = models.DecimalField('مبلغ ودیعه شرکت در حراجی', max_digits=12, decimal_places=0,
                                          default=100000)
    payment_deadline_hours = models.PositiveIntegerField('مهلت پرداخت برنده (ساعت)', default=48)

    class Meta:
        verbose_name = 'حراجی'
        verbose_name_plural = 'حراجی‌ها'
        ordering = ['-start_time']

    def __str__(self):
        return f'حراجی: {self.listing.title}'

    def get_absolute_url(self):
        return reverse('auction_detail', args=[self.pk])

    @property
    def current_price(self):
        top = self.bids.order_by('-amount').first()
        return top.amount if top else self.starting_price

    @property
    def top_bid(self):
        return self.bids.order_by('-amount').first()

    @property
    def is_finished_by_time(self):
        return timezone.now() >= self.end_time

    @property
    def is_active(self):
        return (not self.is_closed) and (not self.is_finished_by_time)

    def close_if_needed(self):
        """اگر زمان تمام شده و هنوز بسته نشده، حراجی را می‌بندد، برنده را مشخص می‌کند،
        سفارش نهایی برنده را می‌سازد و ودیعه بازنده‌ها را آزاد می‌کند."""
        if not self.is_closed and self.is_finished_by_time:
            top = self.top_bid
            if top:
                self.winner = top.bidder
                self.listing.status = Listing.STATUS_SOLD
                self.listing.save()
            self.is_closed = True
            self.save()

            if top:
                self._create_final_order(top)
                self._settle_deposits(winner=top.bidder)
            else:
                self._settle_deposits(winner=None)

    def _create_final_order(self, top_bid):
        winner_deposit = self.deposits.filter(user=self.winner, status=Deposit.STATUS_PAID).first()
        deposit_amount = winner_deposit.amount if winner_deposit else 0

        total_before_deposit = top_bid.amount + self.buyer_premium_amount
        total_payable = max(total_before_deposit - deposit_amount, 0)

        Order.objects.create(
            auction=self,
            buyer=self.winner,
            hammer_price=top_bid.amount,
            buyer_premium=self.buyer_premium_amount,
            deposit_applied=deposit_amount,
            total_payable=total_payable,
            payment_deadline=self.payment_deadline,
        )

        if winner_deposit:
            winner_deposit.status = Deposit.STATUS_APPLIED
            winner_deposit.save(update_fields=['status'])

    def _settle_deposits(self, winner):
        """ودیعه هرکسی که برنده نشده را آزاد (بازگردانده) می‌کند."""
        qs = self.deposits.filter(status=Deposit.STATUS_PAID)
        if winner:
            qs = qs.exclude(user=winner)
        for dep in qs:
            dep.status = Deposit.STATUS_REFUNDED
            dep.save(update_fields=['status'])
            # TODO: اینجا فراخوانی واقعی بازگشت وجه درگاه پرداخت را صدا بزنید

    def minimum_next_bid(self):
        return self.current_price + self.min_increment

    # --- محاسبات مالی کارمزد خریدار ---

    @property
    def buyer_premium_amount(self):
        """کارمزدی که فقط به خریدار اضافه می‌شود (روی قیمت نهایی چکش)"""
        if not self.top_bid:
            return 0
        return (self.top_bid.amount * self.buyer_premium_percent / 100).quantize(Decimal('1'))

    @property
    def final_payable_amount(self):
        """مبلغ کل که برنده باید نهایتاً پرداخت کند = قیمت چکش + کارمزد"""
        if not self.top_bid:
            return None
        return self.top_bid.amount + self.buyer_premium_amount

    @property
    def payment_deadline(self):
        return self.end_time + timezone.timedelta(hours=self.payment_deadline_hours)


class Bid(models.Model):
    auction = models.ForeignKey(Auction, on_delete=models.CASCADE, related_name='bids',
                                 verbose_name='حراجی')
    bidder = models.ForeignKey(User, on_delete=models.CASCADE, related_name='bids',
                                verbose_name='خریدار')
    amount = models.DecimalField('مبلغ پیشنهادی', max_digits=12, decimal_places=0)
    created_at = models.DateTimeField('زمان ثبت', auto_now_add=True)

    class Meta:
        verbose_name = 'پیشنهاد قیمت'
        verbose_name_plural = 'پیشنهادهای قیمت'
        ordering = ['-amount']

    def __str__(self):
        return f'{self.bidder} → {self.amount} تومان'


class Deposit(models.Model):
    """ودیعه‌ای که کاربر برای مجاز شدن به شرکت در یک حراجی خاص پرداخت می‌کند."""
    STATUS_PENDING = 'pending'
    STATUS_PAID = 'paid'
    STATUS_REFUNDED = 'refunded'
    STATUS_FORFEITED = 'forfeited'
    STATUS_APPLIED = 'applied'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'در انتظار تایید درگاه'),
        (STATUS_PAID, 'پرداخت‌شده / فعال'),
        (STATUS_REFUNDED, 'بازگردانده‌شده'),
        (STATUS_FORFEITED, 'ضبط‌شده (جریمه)'),
        (STATUS_APPLIED, 'به سفارش نهایی منظور شد'),
    ]

    auction = models.ForeignKey(Auction, on_delete=models.CASCADE, related_name='deposits',
                                 verbose_name='حراجی')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='deposits',
                              verbose_name='کاربر')
    amount = models.DecimalField('مبلغ ودیعه', max_digits=12, decimal_places=0)
    payment_gateway_ref = models.CharField('کد پیگیری درگاه', max_length=100, blank=True)
    status = models.CharField('وضعیت', max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING)
    created_at = models.DateTimeField('تاریخ ثبت', auto_now_add=True)

    class Meta:
        verbose_name = 'ودیعه'
        verbose_name_plural = 'ودیعه‌ها'
        constraints = [
            models.UniqueConstraint(
                fields=['auction', 'user'],
                condition=models.Q(status='paid'),
                name='unique_active_deposit_per_user_auction',
            )
        ]

    def __str__(self):
        return f'ودیعه {self.amount} از {self.user} برای حراجی #{self.auction_id}'


class Order(models.Model):
    """پرداخت نهایی برنده حراجی، بعد از پایان کار."""
    STATUS_PENDING = 'pending'
    STATUS_PAID = 'paid'
    STATUS_EXPIRED = 'expired'
    STATUS_CANCELLED = 'cancelled'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'در انتظار پرداخت'),
        (STATUS_PAID, 'پرداخت‌شده'),
        (STATUS_EXPIRED, 'مهلت پرداخت گذشته'),
        (STATUS_CANCELLED, 'لغو شده'),
    ]

    auction = models.OneToOneField(Auction, on_delete=models.CASCADE, related_name='order',
                                    verbose_name='حراجی')
    buyer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='orders',
                               verbose_name='خریدار')

    hammer_price = models.DecimalField('قیمت چکش', max_digits=12, decimal_places=0)
    buyer_premium = models.DecimalField('کارمزد خریدار', max_digits=12, decimal_places=0)
    deposit_applied = models.DecimalField('ودیعه کسرشده', max_digits=12, decimal_places=0, default=0)
    total_payable = models.DecimalField('مبلغ باقی‌مانده برای پرداخت', max_digits=12, decimal_places=0)

    status = models.CharField('وضعیت', max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING)
    payment_deadline = models.DateTimeField('مهلت پرداخت')

    payment_gateway_ref = models.CharField('کد پیگیری درگاه', max_length=100, blank=True)
    paid_at = models.DateTimeField('زمان پرداخت', null=True, blank=True)
    created_at = models.DateTimeField('تاریخ ثبت', auto_now_add=True)

    class Meta:
        verbose_name = 'سفارش نهایی'
        verbose_name_plural = 'سفارش‌های نهایی'

    def __str__(self):
        return f'سفارش #{self.pk} برای حراجی #{self.auction_id}'
