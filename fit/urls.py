from django.urls import path
from django.contrib.auth import views as auth_views
from . import views
from .views import register_view

urlpatterns = [
    path('register/', register_view, name='register'),
    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    path('profile/', views.profile, name='profile'),

    path('diet-setup/', views.diet_setup, name='diet_setup'),
    path('water-setup/', views.water_setup, name='water_setup'),
    path('workout-setup/', views.workout_setup, name='workout_setup'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('analysis/', views.analysis, name='analysis'),
    path('', views.dashboard, name='dashboard'),  
]
