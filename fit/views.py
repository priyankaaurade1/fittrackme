from django.shortcuts import render, redirect
from django.contrib.auth.forms import UserCreationForm
from .models import *
from django.contrib.auth.decorators import login_required
from django.utils.text import slugify
from datetime import date, datetime, timedelta
from django.db.models import Q
from decimal import Decimal
from django.conf import settings
import pytz
import json
from django.shortcuts import get_object_or_404
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib import messages
from django.contrib.auth import authenticate, login as auth_login

def auth_combined_view(request):
    login_form = AuthenticationForm()
    register_form = UserCreationForm()
    for form in [login_form, register_form]:
        for field in form.fields.values():
            field.help_text = None
            field.widget.attrs.update({'placeholder': field.label, 'class': 'form-control'})
            field.label = ''
    if request.method == 'POST':
        if 'login' in request.POST:
            login_form = AuthenticationForm(request, data=request.POST)
            if login_form.is_valid():
                auth_login(request, login_form.get_user())
                messages.success(request, "✅ Logged in successfully.")
                return redirect('profile') 
            else:
                messages.error(request, "❌ Invalid username or password.")
        elif 'register' in request.POST:
            register_form = UserCreationForm(request.POST)
            if register_form.is_valid():
                user = register_form.save()
                auth_login(request, user) 
                messages.success(request, "✅ Account created! Please complete your profile.")
                return redirect('profile')  
            else:
                messages.error(request, "❌ Registration failed. Please correct the errors.")
    return render(request, 'registration/auth_combined.html', {
        'login_form': login_form,
        'register_form': register_form,
    })

@login_required
def water_setup(request):
    profile = UserProfile.objects.filter(user=request.user).first()
    if not profile or not profile.height_cm or not profile.current_weight:
        messages.info(request, "Complete your profile first.")
        return redirect('profile')
    target, created = WaterTarget.objects.get_or_create(user=request.user)
    if request.method == "POST":
        measurement_type = request.POST.get("measurement_type")
        unit_volume = int(request.POST.get("unit_volume") or 0)
        quantity_per_day = int(request.POST.get("quantity_per_day") or 0)
        daily_goal = unit_volume * quantity_per_day

        target.measurement_type = measurement_type
        target.unit_volume_ml = unit_volume
        target.quantity_per_day = quantity_per_day
        target.daily_goal_ml = daily_goal
        target.save()

        messages.success(request, "Water goal updated successfully! 💧")

        return redirect("dashboard")

    return render(request, "water_setup.html", {"target": target})

@login_required
def diet_setup(request):
    profile = UserProfile.objects.filter(user=request.user).first()
    if not profile or not profile.height_cm or not profile.current_weight:
        messages.info(request, "Complete your profile first.")
        return redirect('profile')
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
    profile = UserProfile.objects.filter(user=request.user).first()
    if not profile or not profile.height_cm or not profile.current_weight:
        messages.info(request, "Complete your profile first.")
        return redirect('profile')
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
    user = request.user

    # ✅ Ensure profile exists
    profile, created = UserProfile.objects.get_or_create(user=user)
    if not profile.height_cm or not profile.current_weight:
        messages.info(request, "Please complete your profile setup first.")
        return redirect('profile')

    # ✅ Ensure setup completion
    if not DietPlan.objects.filter(user=user).exists():
        return redirect('diet_setup')
    if not WaterTarget.objects.filter(user=user).exists():
        return redirect('water_setup')
    if not WorkoutPlan.objects.filter(user=user).exists():
        return redirect('workout_setup')

    today = timezone.localdate()
    weekday = today.strftime('%A')

    # ✅ Query user data
    diet_qs = DietPlan.objects.filter(user=user)
    workout_qs = WorkoutPlan.objects.filter(user=user, day=weekday)
    progress, _ = DailyProgress.objects.get_or_create(user=user, date=today)

    # ✅ Water setup
    water_target = WaterTarget.objects.filter(user=user).first()
    if water_target:
        water_type = water_target.measurement_type
        water_unit = water_target.unit_volume_ml or 250
        total_ml = water_target.daily_goal_ml or 2000
        total_units = total_ml // water_unit
    else:
        water_type = "glass"
        water_unit = 250
        total_units = 8

    # ✅ Handle POST (save progress)
    if request.method == "POST":
        weight = request.POST.get("today_weight")
        if weight:
            progress.today_weight = Decimal(weight)
            WeightEntry.objects.update_or_create(
                user=user, date=today, defaults={"weight": Decimal(weight)}
            )

        # 🍽️ Save completed foods (checked boxes)
        # ✅ Save all checked foods properly
        selected_foods = [
            v for k, v in request.POST.items()
            if k.startswith("food_")
        ]
        progress.completed_foods = selected_foods

        # 🏋️ Save completed workouts
        completed_workouts = [
            v for k, v in request.POST.items() if k.startswith("workout_")
        ]
        progress.completed_workouts = completed_workouts

        # 💧 Save water glasses
        completed_water = [
            i for i in range(1, total_units + 1)
            if f"water_{i}" in request.POST
        ]
        progress.water_glasses = completed_water

        # ⏰ Save completed routines (optional checkbox in UI)
        completed_routines = [
            r.title for r in DailyRoutine.objects.filter(user=user, is_active=True)
            if f"routine_{r.id}" in request.POST
        ]
        progress.completed_routines = completed_routines

        progress.save()
        messages.success(request, "✅ Progress saved successfully!")
        return redirect("dashboard")

    # ✅ Prepare diet and workouts for template
    diet = {
        d.meal_time: [i.strip() for i in d.food_items.splitlines() if i.strip()]
        for d in diet_qs
    }
    workouts = [
        w.strip() for w in workout_qs[0].exercises.splitlines()
    ] if workout_qs.exists() else []

    # ✅ Calculate total progress %
    total_items = (
        len(workouts)
        + sum(len(v) for v in diet.values())
        + total_units
    )
    completed_items = (
        len(progress.completed_workouts or [])
        + len(progress.completed_foods or [])
        + len(progress.water_glasses or [])
    )
    progress_percent = int((completed_items / total_items) * 100) if total_items else 0

    # ✅ Weight tracking
    recent_weights = list(WeightEntry.objects.filter(user=user).order_by('-date')[:7])[::-1]
    weights = [float(w.weight) for w in recent_weights]
    labels = [w.date.strftime("%d %b") for w in recent_weights]
    weight_diff = (
        round(float(recent_weights[-1].weight) - float(recent_weights[-2].weight), 1)
        if len(recent_weights) >= 2 else 0
    )

    # ✅ BMI + Motivation
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
        motivation = "Update your height and weight to calculate BMI."

    user_height = profile.height_cm
    yesterday_weight = weights[-2] if len(weights) >= 2 else None

    # ✅ Timezone-safe routine handling
    tz = pytz.timezone(getattr(settings, "TIME_ZONE", "Asia/Kolkata"))
    now = timezone.now().astimezone(tz)
    routines = DailyRoutine.objects.filter(user=user, is_active=True).order_by('time')

    today_routines = []
    for r in routines:
        routine_time = datetime.combine(today, r.time)
        routine_time = timezone.make_aware(routine_time, tz)
        now_local = timezone.localtime(timezone.now(), tz)
        diff_minutes = int((routine_time - now_local).total_seconds() / 60)

        if diff_minutes > 0:
            status = f"{diff_minutes} min left"
        elif -30 <= diff_minutes <= 0:
            status = "⏰ It's time!"
        else:
            status = "✅ Done"

        today_routines.append({
            "id": r.id,
            "title": r.title,
            "time": r.time.strftime("%I:%M %p"),
            "description": r.description,
            "status": status,
            "is_done": r.title in (progress.completed_routines or [])
        })

    # ✅ Final context
    context = {
        'today': today,
        'diet': diet,
        'workouts': workouts,
        'progress': progress,
        'water_type': water_type,
        'total_units': total_units,
        'water_unit_range': range(1, total_units + 1),
        'progress_percent': progress_percent,
        'weights': weights,
        'labels': labels,
        'weight_diff': weight_diff,
        'bmi': bmi,
        'motivation': motivation,
        'user_height': user_height,
        'yesterday_weight': yesterday_weight,
        'today_routines': today_routines,
        'timezone': str(tz),
    }

    return render(request, 'dashboard.html', context)

@login_required
def analysis(request):
    user = request.user
    today = date.today()
    range_option = request.GET.get("range", "week")  # default to week for meaningful data
    selected_range = range_option

    # ⏱ Calculate Date Range
    if range_option == "day":
        start_date = today
        end_date = today
    elif range_option == "week":
        start_date = today - timedelta(days=today.weekday())  # Monday
        end_date = today
    elif range_option == "month":
        start_date = today.replace(day=1)
        end_date = today
    elif range_option == "year":
        start_date = today.replace(month=1, day=1)
        end_date = today
    else:
        start_date = WeightEntry.objects.filter(user=user).first().date if WeightEntry.objects.filter(user=user).exists() else today
        end_date = today

    # 📅 Filter Progress Entries
    progress_entries = DailyProgress.objects.filter(user=user, date__range=[start_date, end_date]).order_by('date')
    total_days = (end_date - start_date).days + 1
    entry_dates = {entry.date: entry for entry in progress_entries}

    # ✅ Prepare meal/workout/water stats
    meal_completed_days = 0
    workout_days = 0
    water_data = []
    water_labels = []
    bar_labels = []
    meal_bar_data = []
    workout_bar_data = []

    for i in range(total_days):
        current = start_date + timedelta(days=i)
        bar_labels.append(current.strftime("%a %d"))
        entry = entry_dates.get(current)

        if entry:
            if entry.meals_completed:
                meal_completed_days += 1
                meal_bar_data.append(1)
            else:
                meal_bar_data.append(0)

            if entry.completed_workouts:
                workout_days += 1
                workout_bar_data.append(1)
            else:
                workout_bar_data.append(0)

            water_count = len(entry.water_glasses)
            water_data.append(water_count)
        else:
            meal_bar_data.append(0)
            workout_bar_data.append(0)
            water_data.append(0)

        water_labels.append(current.strftime("%d %b"))

    meal_percent = int((meal_completed_days / total_days) * 100) if total_days else 0
    workout_percent = int((workout_days / total_days) * 100) if total_days else 0
    average_water = round(sum(water_data) / total_days, 1) if total_days else 0

    # ⚖️ Weight Entries
    weight_entries = WeightEntry.objects.filter(user=user, date__range=[start_date, end_date]).order_by('date')
    weight_labels = [w.date.strftime("%d %b") for w in weight_entries]
    weight_values = [float(w.weight) for w in weight_entries]
    weight_chart = {
        'labels': json.dumps(weight_labels),
        'data': json.dumps(weight_values),
    }
    weight_change = 0
    if weight_entries.count() >= 2:
        weight_change = round(weight_entries.last().weight - weight_entries.first().weight, 1)

    context = {
        'selected_range': selected_range,
        'meal_completion_percent': meal_percent,
        'workout_completion_percent': workout_percent,
        'meal_completed_days': meal_completed_days,
        'workout_days': workout_days,
        'total_days': total_days,
        'meal_remaining_percent': 100 - meal_percent,
        'workout_remaining_percent': 100 - workout_percent,
        'average_water': average_water,
        'water_goal_glasses': 12,
        'water_goal_liters': round(12 * 250 / 1000, 1),
        'water_chart': {
            'labels': json.dumps(water_labels),
            'data': json.dumps(water_data)
        },
        'weight_chart': weight_chart,
        'bar_labels': json.dumps(bar_labels),
        'meal_bar_data': json.dumps(meal_bar_data),
        'workout_bar_data': json.dumps(workout_bar_data),
        'first_weight': weight_entries.first().weight if weight_entries else 'N/A',
        'last_weight': weight_entries.last().weight if weight_entries else 'N/A',
        'weight_change': weight_change,
    }
    return render(request, 'analysis.html', context)

@login_required
def profile(request):
    user = request.user
    profile, created = UserProfile.objects.get_or_create(user=user)

    if request.method == 'POST':
        profile.full_name = request.POST.get('full_name') or user.username
        profile.age = request.POST.get('age')
        profile.sex = request.POST.get('sex')
        profile.height_cm = request.POST.get('height_cm')
        profile.current_weight = request.POST.get('current_weight')
        profile.save()
        messages.success(request, "✅ Profile updated.")
        return redirect('diet_setup')

    return render(request, 'profile.html', {
        'profile': profile,
    })

@login_required
def routine_setup(request):
    if request.method == "POST":
        title = request.POST.get("title")
        description = request.POST.get("description")
        time = request.POST.get("time")

        DailyRoutine.objects.create(
            user=request.user,
            title=title,
            description=description,
            time=time
        )
        messages.success(request, "Routine added successfully! ⏰")
        return redirect("routine_setup")

    routines = DailyRoutine.objects.filter(user=request.user).order_by("time")
    return render(request, "routine_setup.html", {"routines": routines})

@login_required
def edit_routine(request):
    if request.method == "POST":
        rid = request.POST.get("routine_id")
        title = request.POST.get("title")
        time = request.POST.get("time")
        description = request.POST.get("description")

        # Ensure routine_id was passed correctly
        if not rid:
            messages.error(request, "❌ Routine missing — please try again.")
            return redirect("routine_setup")

        try:
            routine = DailyRoutine.objects.get(id=rid, user=request.user)
        except DailyRoutine.DoesNotExist:
            messages.error(request, "⚠️ Routine not found or you don’t have permission to edit it.")
            return redirect("routine_setup")

        # ✅ Update existing record
        routine.title = title
        routine.time = time
        routine.description = description
        routine.save()

        messages.success(request, "✏️ Routine updated successfully!")
        return redirect("routine_setup")

@login_required
def delete_routine(request, routine_id):
    routine = DailyRoutine.objects.filter(id=routine_id, user=request.user).first()
    if routine:
        routine.delete()
        messages.success(request, "🗑️ Routine deleted successfully!")
    return redirect("routine_setup")

@login_required
def journal_view(request):
    today = timezone.localdate()
    today_entry = DailyJournal.objects.filter(user=request.user, date=today).first()

    if request.method == "POST":
        mood = request.POST.get("mood")
        note = request.POST.get("note")

        # 🧠 Check if today's entry already exists
        if today_entry:
            # Don't overwrite it — show message instead
            messages.warning(
                request,
                "⚠️ You’ve already written your journal for today! If you want to make changes, please edit/delete your entry."
            )
            return redirect("journal_view")  # redirect back safely

        # ✅ If no entry yet — create a new one
        DailyJournal.objects.create(
            user=request.user,
            date=today,
            mood=mood,
            note=note
        )
        messages.success(request, "💾 Journal saved successfully!")
        return redirect("journal_view")

    all_entries = DailyJournal.objects.filter(user=request.user).order_by("-date")
    return render(request, "journal.html", {
        "today_entry": today_entry,
        "all_entries": all_entries,
    })

@login_required
def edit_journal(request):
    if request.method == "POST":
        entry_id = request.POST.get("entry_id")
        mood = request.POST.get("mood")
        note = request.POST.get("note")

        entry = DailyJournal.objects.get(id=entry_id, user=request.user)
        entry.mood = mood
        entry.note = note
        entry.save()
        messages.success(request, "✏️ Journal updated successfully!")
    return redirect("journal_view")

@login_required
def delete_journal(request, entry_id):
    entry = DailyJournal.objects.filter(id=entry_id, user=request.user).first()
    if entry:
        entry.delete()
        messages.success(request, "🗑️ Journal deleted successfully!")
    return redirect("journal_view")
