from django.db import models
from django.contrib.auth.models import User
from datetime import date

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    full_name = models.CharField(max_length=100, blank=True)
    age = models.PositiveIntegerField(null=True, blank=True)
    sex = models.CharField(max_length=10, choices=[('male', 'Male'), ('female', 'Female')], blank=True)
    height_cm = models.FloatField(null=True, blank=True)
    current_weight = models.FloatField(null=True, blank=True)

    @property
    def bmi(self):
        if self.height_cm and self.current_weight:
            height_m = self.height_cm / 100
            return round(self.current_weight / (height_m ** 2), 1)
        return None

DAYS_OF_WEEK = [
    ("Monday", "Monday"),
    ("Tuesday", "Tuesday"),
    ("Wednesday", "Wednesday"),
    ("Thursday", "Thursday"),
    ("Friday", "Friday"),
    ("Saturday", "Saturday"),
    ("Sunday", "Sunday"),
]

class DietPlan(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    meal_time = models.CharField(max_length=50)
    food_items = models.TextField()

class WaterTarget(models.Model):
    MEASUREMENT_CHOICES = [
        ('glass', 'Glass'),
        ('bottle', 'Bottle'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    measurement_type = models.CharField(max_length=10, choices=MEASUREMENT_CHOICES, default='glass')
    unit_volume_ml = models.PositiveIntegerField(default=0)  
    quantity_per_day = models.PositiveIntegerField(default=0)
    daily_goal_ml = models.PositiveIntegerField(default=0)  

class WorkoutPlan(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    day = models.CharField(max_length=10, choices=DAYS_OF_WEEK)
    exercises = models.TextField()

class DailyProgress(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    date = models.DateField(default=date.today)
    meals_completed = models.JSONField(default=dict)  
    completed_foods = models.JSONField(default=list) 
    completed_workouts = models.JSONField(default=list)
    water_glasses = models.JSONField(default=list)
    today_weight = models.FloatField(null=True, blank=True) 

class WeightEntry(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    date = models.DateField(auto_now_add=True)
    weight = models.DecimalField(max_digits=5, decimal_places=2)

    def __str__(self):
        return f"{self.user.username} - {self.weight} kg on {self.date}"
