from django.urls import path
from django.contrib.auth import views as auth_views
from . import views
from django.contrib.auth.views import LogoutView
urlpatterns = [
    path('login/', views.auth_combined_view, name='login'), 
    path('register/', views.auth_combined_view, name='register'),  
    path('logout/', LogoutView.as_view(next_page='login'), name='logout'),
    path('profile/', views.profile, name='profile'),

    path('diet-setup/', views.diet_setup, name='diet_setup'),
    path('water-setup/', views.water_setup, name='water_setup'),
    path('workout-setup/', views.workout_setup, name='workout_setup'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('analysis/', views.analysis, name='analysis'),
    path('', views.dashboard, name='dashboard'),  
    path('routine-setup/', views.routine_setup, name='routine_setup'),
    path("routine/edit/", views.edit_routine, name="edit_routine"),
    path("routine/delete/<int:routine_id>/", views.delete_routine, name="delete_routine"),

    path('journal/', views.journal_view, name='journal_view'),
    path("journal/edit/", views.edit_journal, name="edit_journal"),
    path("journal/delete/<int:entry_id>/", views.delete_journal, name="delete_journal"),
    path('delete-diet-item/', views.delete_diet_item, name='delete_diet_item'),
    path('delete-workout-item/', views.delete_workout_item, name='delete_workout_item'),

]
