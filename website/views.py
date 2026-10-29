import json
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse, HttpResponseBadRequest
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST, require_http_methods
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from .models import Order, Consultation, UserProfile
from .forms import RegisterForm, ProfileForm, UserProfileForm
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction

@ensure_csrf_cookie
def home(request):
    return render(request, 'website/index.html')

def staff_login(request):
    if request.user.is_authenticated and request.user.is_staff:
        return redirect('dashboard')
    error = ''
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        if user is not None and user.is_staff:
            login(request, user)
            return redirect('dashboard')
        error = 'Username atau password salah, atau akun bukan admin.'
    return render(request, 'registration/staff_login.html', {'error': error})

def staff_logout(request):
    if request.method == 'POST':
        logout(request)
    return redirect('home')

@staff_member_required(login_url='staff_login')
def dashboard(request):
    orders = Order.objects.all().order_by('-created_at')
    consultations = Consultation.objects.all().order_by('-created_at')
    return render(request, 'website/admin.html', {
        'orders': orders, 'consultations': consultations,
        'total_orders': orders.count(),
        'revenue': sum(o.total for o in orders),
        'pending_orders': orders.filter(status='Menunggu konfirmasi').count(),
    })

def json_body(request):
    try:
        return json.loads(request.body.decode('utf-8') or '{}')
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None

@require_POST
def orders_api(request):
    data = json_body(request)
    if data is None:
        return HttpResponseBadRequest('JSON tidak valid.')
    required = ['name', 'email', 'phone', 'payment', 'items']
    if any(not data.get(key) for key in required):
        return JsonResponse({'error': 'Lengkapi nama, email, nomor WhatsApp, metode pembayaran, dan paket.'}, status=400)
    try:
        validate_email(str(data['email']).strip())
    except ValidationError:
        return JsonResponse({'error': 'Format email tidak valid.'}, status=400)
    if data['payment'] not in ['QRIS (demo)', 'Virtual Account (demo)', 'Transfer bank manual (demo)']:
        return JsonResponse({'error': 'Metode pembayaran tidak valid.'}, status=400)
    if not isinstance(data['items'], list) or not data['items']:
        return JsonResponse({'error': 'Keranjang pesanan kosong atau tidak valid.'}, status=400)
    # Prices are validated and calculated server-side from the allowed package catalog.
    allowed = {
        'Brand Starter': 750000,
        'Social Boost': 1500000,
        'Campaign Kit': 2500000,
    }
    cleaned_items = []
    for item in data['items']:
        if not isinstance(item, dict) or item.get('name') not in allowed:
            return JsonResponse({'error': 'Ada paket yang tidak dikenal. Muat ulang halaman dan coba lagi.'}, status=400)
        name = item['name']
        cleaned_items.append({'name': name, 'price': allowed[name]})
    total = sum(item['price'] for item in cleaned_items)
    order = Order.objects.create(
        name=str(data['name']).strip()[:120], email=str(data['email']).strip(),
        phone=str(data['phone']).strip()[:40], notes=str(data.get('notes', '')).strip(),
        payment_method=str(data['payment']).strip()[:80], items=cleaned_items, total=total,
    )
    return JsonResponse({'id': order.reference, 'name': order.name, 'status': order.status}, status=201)

@staff_member_required(login_url='staff_login')
@require_GET
def orders_list_api(request):
    return JsonResponse({'orders': [order_to_dict(o) for o in Order.objects.all().order_by('-created_at')]})

def order_to_dict(o):
    return {'id': o.id, 'reference': o.reference, 'date': o.created_at.isoformat(), 'name': o.name,
            'email': o.email, 'phone': o.phone, 'notes': o.notes, 'payment': o.payment_method,
            'items': o.items, 'total': o.total, 'status': o.status}

@staff_member_required(login_url='staff_login')
@require_http_methods(['PATCH', 'DELETE'])
def order_detail_api(request, order_id):
    order = get_object_or_404(Order, pk=order_id)
    if request.method == 'DELETE':
        order.delete()
        return JsonResponse({'ok': True})
    data = json_body(request)
    if not data or data.get('status') not in dict(Order.STATUS_CHOICES):
        return JsonResponse({'error': 'Status tidak valid.'}, status=400)
    order.status = data['status']; order.save(update_fields=['status'])
    return JsonResponse({'ok': True, 'status': order.status})

@require_POST
def submit_consultation(request):
    data = json_body(request)
    if data is None:
        return HttpResponseBadRequest('JSON tidak valid.')
    required = ['name', 'email', 'service', 'budget', 'brief']
    if any(not str(data.get(key, '')).strip() for key in required):
        return JsonResponse({'error': 'Semua data konsultasi wajib diisi.'}, status=400)
    try:
        validate_email(str(data['email']).strip())
    except ValidationError:
        return JsonResponse({'error': 'Format email tidak valid.'}, status=400)
    if len(str(data['brief']).strip()) < 10:
        return JsonResponse({'error': 'Brief minimal 10 karakter.'}, status=400)
    consultation = Consultation.objects.create(
        name=str(data['name']).strip()[:120], email=str(data['email']).strip(),
        service=str(data['service']).strip()[:120], budget=str(data['budget']).strip()[:100],
        brief=str(data['brief']).strip(),
    )
    return JsonResponse({'id': consultation.reference, 'name': consultation.name, 'status': consultation.status}, status=201)

@staff_member_required(login_url='staff_login')
@require_GET
def consultations_api(request):
    return JsonResponse({'consultations': [
        {'id': c.id, 'reference': c.reference, 'date': c.created_at.isoformat(), 'name': c.name,
         'email': c.email, 'service': c.service, 'budget': c.budget, 'brief': c.brief, 'status': c.status}
        for c in Consultation.objects.all().order_by('-created_at')
    ]})

@staff_member_required(login_url='staff_login')
@require_POST
def update_order_status(request, order_id):
    order = get_object_or_404(Order, pk=order_id)
    status = request.POST.get('status')
    if status in dict(Order.STATUS_CHOICES):
        order.status = status
        order.save(update_fields=['status'])
        messages.success(request, f'Status pesanan {order.reference} diperbarui.')
    else:
        messages.error(request, 'Status pesanan tidak valid.')
    return redirect('dashboard')

@staff_member_required(login_url='staff_login')
@require_POST
def delete_order(request, order_id):
    order = get_object_or_404(Order, pk=order_id)
    reference = order.reference
    order.delete()
    messages.success(request, f'Pesanan {reference} dihapus.')
    return redirect('dashboard')


def register(request):
    if request.user.is_authenticated:
        return redirect('user_dashboard')
    form = RegisterForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        UserProfile.objects.get_or_create(user=user)
        login(request, user)
        messages.success(request, 'Akun berhasil dibuat. Selamat datang di Socialyze!')
        return redirect('user_dashboard')
    return render(request, 'website/register.html', {'form': form})


def user_login(request):
    if request.user.is_authenticated:
        return redirect('dashboard' if request.user.is_staff else 'user_dashboard')
    error = ''
    if request.method == 'POST':
        user = authenticate(request, username=request.POST.get('username', '').strip(), password=request.POST.get('password', ''))
        if user is not None:
            login(request, user)
            return redirect('dashboard' if user.is_staff else 'user_dashboard')
        error = 'Username atau password salah.'
    return render(request, 'website/login.html', {'error': error})


@login_required
@require_http_methods(['GET', 'POST'])
def user_dashboard(request):
    if request.user.is_staff:
        return redirect('dashboard')
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    if request.method == 'POST':
        user_form = ProfileForm(request.POST, instance=request.user)
        profile_form = UserProfileForm(request.POST, instance=profile)
        if user_form.is_valid() and profile_form.is_valid():
            user_form.save()
            profile_form.save()
            messages.success(request, 'Profil berhasil diperbarui.')
            return redirect('user_dashboard')
    else:
        user_form = ProfileForm(instance=request.user)
        profile_form = UserProfileForm(instance=profile)
    orders = Order.objects.filter(email__iexact=request.user.email).order_by('-created_at') if request.user.email else Order.objects.none()
    return render(request, 'website/user_dashboard.html', {'user_form': user_form, 'profile_form': profile_form, 'orders': orders})


@login_required
@require_http_methods(['GET', 'POST'])
def admin_profile(request):
    if not request.user.is_staff:
        return redirect('user_dashboard')
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    if request.method == 'POST':
        user_form = ProfileForm(request.POST, instance=request.user)
        profile_form = UserProfileForm(request.POST, instance=profile)
        if user_form.is_valid() and profile_form.is_valid():
            user_form.save()
            profile_form.save()
            messages.success(request, 'Profil admin berhasil diperbarui.')
            return redirect('admin_profile')
    else:
        user_form = ProfileForm(instance=request.user)
        profile_form = UserProfileForm(instance=profile)
    return render(request, 'website/profile.html', {'user_form': user_form, 'profile_form': profile_form, 'heading': 'Perbarui Profil Admin', 'back_url': 'dashboard'})
