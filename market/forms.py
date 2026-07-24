from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.utils import timezone
from .models import Listing, Auction, Bid


class BootstrapFormMixin:
    """به همه‌ی فیلدها کلاس‌های بوت‌استرپ اضافه می‌کند."""

    def _apply_bootstrap(self):
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.Select):
                existing = widget.attrs.get('class', '')
                widget.attrs['class'] = (existing + ' form-select').strip()
            elif isinstance(widget, forms.CheckboxInput):
                existing = widget.attrs.get('class', '')
                widget.attrs['class'] = (existing + ' form-check-input').strip()
            else:
                existing = widget.attrs.get('class', '')
                widget.attrs['class'] = (existing + ' form-control').strip()


class RegisterForm(BootstrapFormMixin, UserCreationForm):
    email = forms.EmailField(required=False, label='ایمیل')

    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_bootstrap()


class ListingForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Listing
        fields = ['title', 'description', 'price', 'category', 'image']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 5}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_bootstrap()


class AuctionForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Auction
        fields = ['starting_price', 'min_increment', 'end_time']
        widgets = {
            'end_time': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_bootstrap()

    def clean_end_time(self):
        end_time = self.cleaned_data['end_time']
        if end_time <= timezone.now():
            raise forms.ValidationError('زمان پایان حراجی باید در آینده باشد.')
        return end_time


class BidForm(BootstrapFormMixin, forms.Form):
    amount = forms.DecimalField(label='مبلغ پیشنهادی (تومان)', max_digits=12, decimal_places=0)

    def __init__(self, *args, auction=None, **kwargs):
        self.auction = auction
        super().__init__(*args, **kwargs)
        self._apply_bootstrap()
        if auction is not None:
            self.fields['amount'].widget.attrs['min'] = str(auction.minimum_next_bid())
            self.fields['amount'].widget.attrs['placeholder'] = f'حداقل {int(auction.minimum_next_bid())} تومان'

    def clean_amount(self):
        amount = self.cleaned_data['amount']
        if self.auction is not None and amount < self.auction.minimum_next_bid():
            raise forms.ValidationError(
                f'مبلغ پیشنهادی باید حداقل {int(self.auction.minimum_next_bid())} تومان باشد.'
            )
        return amount
