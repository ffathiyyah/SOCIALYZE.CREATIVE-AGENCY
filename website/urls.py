from django.urls import path
from . import views
urlpatterns = [
    path('', views.home, name='home'),
    path('register/', views.register, name='register'),
    path('login/', views.user_login, name='user_login'),
    path('logout/', views.staff_logout, name='staff_logout'),
    path('staff-login/', views.staff_login, name='staff_login'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('my-dashboard/', views.user_dashboard, name='user_dashboard'),
    path('admin-profile/', views.admin_profile, name='admin_profile'),
    path('api/orders/', views.orders_api, name='orders_api'),
    path('api/orders/<int:order_id>/', views.order_detail_api, name='order_detail_api'),
    path('api/consultations/', views.submit_consultation, name='consultations_api'),
    path('api/admin/consultations/', views.consultations_api, name='admin_consultations_api'),
    path('dashboard/orders/<int:order_id>/status/', views.update_order_status, name='update_order_status'),
    path('dashboard/orders/<int:order_id>/delete/', views.delete_order, name='delete_order'),
]
