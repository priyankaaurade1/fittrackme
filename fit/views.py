from django.shortcuts import render, redirect
from django.contrib.auth.forms import UserCreationForm
from .models import *
from django.contrib.auth.decorators import login_required
from django.utils.text import slugify
from datetime import date, timedelta
from django.db.models import Q
from decimal import Decimal
import json

def register_view(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('login')
    else:
        form = UserCreationForm()
    return render(request, 'registration/register.html', {'form': form})

@login_required
def water_setup(request):
    if request.method == 'POST':
        measure_type = request.POST.get('measurement_type')
        unit_volume = int(request.POST.get('unit_volume') or 250)
        quantity = int(request.POST.get('quantity_per_day') or 8)
        total_ml = unit_volume * quantity

        WaterTarget.objects.update_or_create(
            user=request.user,
            defaults={
                "measurement_type": measure_type,
                "unit_volume_ml": unit_volume,
                "quantity_per_day": quantity,
                "daily_goal_ml": total_ml
            }
        )
        return redirect('workout_setup')

    target = WaterTarget.objects.filter(user=request.user).first()
    return render(request, 'water_setup.html', {'target': target})

@login_required
def diet_setup(request):
    meal_times = [
        "Waking Meal", "Breakfast", "Mid-Morning Snack", "Lunch",
        "Evening Snack", "Dinner", "Before Bed"
    ]

    if request.method == 'POST':
        DietPlan.objects.filter(user=request.user).delete()

        for meal in meal_times:
            meal_slug = meal.lower().replace(' ', '-')
            food_items = []

            for key, value in request.POST.items():
                if key.startswith(f"{meal_slug}_item_") and value.strip():
                    food_items.append(value.strip())

            if food_items:
                DietPlan.objects.create(
                    user=request.user,
                    meal_time=meal,
                    food_items="\n".join(food_items)
                )

        return redirect('water_setup')

    # Prepare initial data
    existing = DietPlan.objects.filter(user=request.user)
    meal_data = []
    for meal in meal_times:
        match = next((e.food_items for e in existing if e.meal_time == meal), '')
        meal_data.append((meal, match))

    return render(request, 'diet_setup.html', {
        'meal_data': meal_data
    })

@login_required
def workout_setup(request):
    weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

    if request.method == 'POST':
        WorkoutPlan.objects.filter(user=request.user).delete()
        
        for day in weekdays:
            slugified = slugify(day)
            exercise_list = request.POST.getlist(slugified)
            clean_list = [e.strip() for e in exercise_list if e.strip()]
            if clean_list:
                WorkoutPlan.objects.create(
                    user=request.user,
                    day=day,
                    exercises="\n".join(clean_list)
                )
        return redirect('dashboard')

    # Fetch existing workouts and format them
    existing = WorkoutPlan.objects.filter(user=request.user)
    existing_data = []
    for day in weekdays:
        match = next((e.exercises for e in existing if e.day == day), '')
        exercise_list = [e.strip() for e in match.splitlines() if e.strip()]
        existing_data.append((day, exercise_list))

    return render(request, 'workout_setup.html', {
        'workout_data': existing_data
    })

@login_required
def dashboard(request):
    today = date.today()
    weekday = today.strftime('%A')
    user = request.user

    # Fetch plans
    diet_qs = DietPlan.objects.filter(user=user)
    workout_qs = WorkoutPlan.objects.filter(user=user, day=weekday)
    water_target = WaterTarget.objects.filter(user=user).first()
    water_target_glasses = int(water_target.daily_goal_ml / 250) if water_target else 8
    water_type = water_target.measurement_type if water_target else "glass"

    # Get or create today's progress
    progress, _ = DailyProgress.objects.get_or_create(user=user, date=today)

    if request.method == 'POST':
        # Save weight
        weight = request.POST.get("today_weight")
        if weight:
            progress.today_weight = Decimal(weight)
            WeightEntry.objects.update_or_create(user=user, date=today, defaults={"weight": Decimal(weight)})

        # Save completed foods
        all_foods = [item.strip() for d in diet_qs for item in d.food_items.splitlines() if item.strip()]
        selected_foods = []
        for food in all_foods:
            key = f"food_{food.lower().replace(' ', '-')}"
            if key in request.POST:
                selected_foods.append(food)
        progress.completed_foods = selected_foods

        # Save completed workouts
        selected_workouts = [value for key, value in request.POST.items() if key.startswith("workout_")]
        progress.completed_workouts = selected_workouts

        # Save water intake
        selected_water = [i for i in range(1, water_target_glasses + 1) if f"water_{i}" in request.POST]
        progress.water_glasses = selected_water

        progress.save()
        return redirect("dashboard")

    # Organize diet by meal
    diet = {}
    for d in diet_qs:
        items = [item.strip() for item in d.food_items.splitlines() if item.strip()]
        diet[d.meal_time] = items

    workouts = []
    if workout_qs.exists():
        workouts = [ex.strip() for ex in workout_qs[0].exercises.splitlines() if ex.strip()]

    # Calculate progress percentage
    total_items = len(workouts) + sum(len(v) for v in diet.values()) + water_target_glasses
    completed_items = (
        len(progress.completed_workouts or []) +
        len(progress.completed_foods or []) +
        len(progress.water_glasses or [])
    )
    progress_percent = int((completed_items / total_items) * 100) if total_items > 0 else 0

    # Weight history (last 7 days)
    recent_weights = WeightEntry.objects.filter(user=user).order_by('-date')[:7]
    recent_weights = list(recent_weights)[::-1]  # oldest to newest
    weights = [float(w.weight) for w in recent_weights]
    labels = [w.date.strftime("%d %b") for w in recent_weights]

    # Compare today vs yesterday
    weight_diff = None
    if len(recent_weights) >= 2:
        weight_diff = round(float(recent_weights[-1].weight) - float(recent_weights[-2].weight), 1)

    # BMI & Motivation
    try:
        profile = UserProfile.objects.get(user=user)
        bmi = profile.bmi
        if bmi:
            if bmi < 18.5:
                motivation = "You're underweight. Let’s build strength! 💪"
            elif 18.5 <= bmi < 25:
                motivation = "Healthy range! Keep it up! 🥗"
            elif 25 <= bmi < 30:
                motivation = "Slightly overweight. Let's trim it down! 🏃"
            else:
                motivation = "Obese category. Take care of your health. ❤️"
        else:
            bmi = None
            motivation = "Update height and weight to calculate BMI."
    except UserProfile.DoesNotExist:
        bmi = None
        motivation = "Update your profile to get BMI and suggestions."

    context = {
        'today': today,
        'diet': diet,
        'workouts': workouts,
        'water_target_glasses': water_target_glasses,
        'progress': progress,
        'water_glass_range': range(1, water_target_glasses + 1),
        'water_type': water_type,
        'progress_percent': progress_percent,
        'weights': weights,
        'labels': labels,
        'weight_diff': weight_diff,
        'bmi': bmi,
        'motivation': motivation,
    }
    return render(request, 'dashboard.html', context)

@login_required
def analysis(request):
    today = date.today()
    range_option = request.GET.get("range", "day")
    selected_range = range_option

    # Date range filter
    if range_option == "day":
        entries = DailyProgress.objects.filter(user=request.user, date=today)
    elif range_option == "week":
        start = today - timedelta(days=today.weekday())
        entries = DailyProgress.objects.filter(user=request.user, date__gte=start)
    elif range_option == "month":
        entries = DailyProgress.objects.filter(user=request.user, date__month=today.month, date__year=today.year)
    elif range_option == "year":
        entries = DailyProgress.objects.filter(user=request.user, date__year=today.year)
    else:
        entries = DailyProgress.objects.filter(user=request.user)

    total_days = entries.count()
    meal_completed_days = sum(1 for e in entries if e.meals_completed)
    workout_days = sum(1 for e in entries if e.completed_workouts)

    meal_completion_percent = int((meal_completed_days / total_days) * 100) if total_days else 0
    workout_completion_percent = int((workout_days / total_days) * 100) if total_days else 0

    meal_remaining_percent = 100 - meal_completion_percent
    workout_remaining_percent = 100 - workout_completion_percent

    # 📊 Water Chart Data
    water_labels = [e.date.strftime("%d %b") for e in entries]
    water_values = [len(e.water_glasses) for e in entries]
    average_water = round(sum(water_values) / len(water_values), 1) if water_values else 0

    # You can customize these based on user settings later
    water_goal_glasses = 12  # Default: 12 glasses = 3 liters
    water_goal_liters = round(water_goal_glasses * 250 / 1000, 1)  # 250ml per glass → liters

    water_chart = {
        'labels': json.dumps(water_labels),
        'data': json.dumps(water_values)
    }

    # ⚖️ Weight Tracking
    weight_entries = WeightEntry.objects.filter(user=request.user).order_by('date')
    if range_option == "day":
        weight_entries = weight_entries.filter(date=today)
    elif range_option == "week":
        start = today - timedelta(days=today.weekday())
        weight_entries = weight_entries.filter(date__gte=start)
    elif range_option == "month":
        weight_entries = weight_entries.filter(date__month=today.month, date__year=today.year)
    elif range_option == "year":
        weight_entries = weight_entries.filter(date__year=today.year)

    weight_labels = [w.date.strftime("%d %b") for w in weight_entries]
    weight_values = [float(w.weight) for w in weight_entries]

    weight_chart = {
        'labels': json.dumps(weight_labels),
        'data': json.dumps(weight_values)
    }

    last_weight = weight_entries.last().weight if weight_entries.exists() else "N/A"
    first_weight = weight_entries.first().weight if weight_entries.exists() else "N/A"

    bar_labels = []
    meal_bar_data = []
    workout_bar_data = []

    for e in entries.order_by('date'):
        bar_labels.append(e.date.strftime("%a"))  # Short day: 'Mon', 'Tue'
        meal_bar_data.append(1 if e.meals_completed else 0)
        workout_bar_data.append(1 if e.completed_workouts else 0)

    return render(request, 'analysis.html', {
        'selected_range': selected_range,
        'meal_completion_percent': meal_completion_percent,
        'workout_completion_percent': workout_completion_percent,
        'meal_completed_days': meal_completed_days,
        'workout_days': workout_days,
        'total_days': total_days,
        'water_chart': water_chart,
        'average_water': average_water,
        'water_goal_glasses': water_goal_glasses,
        'water_goal_liters': water_goal_liters,
        'weight_chart': weight_chart,
        'last_weight': last_weight,
        'first_weight': first_weight,
        'bar_labels': json.dumps(bar_labels),
        'meal_bar_data': json.dumps(meal_bar_data),
        'workout_bar_data': json.dumps(workout_bar_data),
        'meal_remaining_percent': meal_remaining_percent,
        'workout_remaining_percent': workout_remaining_percent,
    })

@login_required
def profile(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        profile.full_name = request.POST.get('full_name', '')
        profile.age = int(request.POST.get('age') or 0)
        profile.sex = request.POST.get('sex', '')
        profile.height_cm = float(request.POST.get('height_cm') or 0)
        profile.current_weight = float(request.POST.get('current_weight') or 0)
        profile.save()
        return redirect('profile')

    return render(request, 'profile.html', {'profile': profile})
