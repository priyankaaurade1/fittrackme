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
from datetime import time

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

def auto_sync_routines(user):
    """
    Auto-create or update routines from user's diet & workout plans.
    Safely avoids duplicates using title + start_time + end_time.
    """
    from datetime import time
    from django.utils.timezone import now
    from .models import DietPlan, WorkoutPlan, DailyRoutine

    diet_plans = DietPlan.objects.filter(user=user)
    workouts = WorkoutPlan.objects.filter(user=user)

    # Utility: suggest default meal/workout times (customizable)
    def suggest_meal_time(meal_name):
        meal_name = meal_name.lower()
        if "waking" in meal_name:
            return time(4, 50), time(5, 0)
        elif "pre" in meal_name:
            return time(5, 0), time(5, 30)
        elif "post" in meal_name:
            return time(6, 30), time(6, 45)
        elif "breakfast" in meal_name:
            return time(8, 15), time(8, 45)
        elif "lunch" in meal_name:
            return time(13, 30), time(14, 0)
        elif "evening" in meal_name:
            return time(16, 45), time(17, 0)
        elif "dinner" in meal_name:
            return time(20, 30), time(21, 0)
        elif "bed" in meal_name:
            return time(21, 30), time(22, 0)
        return time(7, 0), time(7, 15)

    # 🥗 Diet → Routine
    for d in diet_plans:
        title = d.meal_time.strip()
        start, end = suggest_meal_time(d.meal_time)
        DailyRoutine.objects.update_or_create(
            user=user,
            title=title,
            start_time=start,  # 👈 uniquely identifies per title+time
            end_time=end,
            defaults={
                "description": f"{d.day} diet: {d.food_items[:150]}...",
                "days": [d.day],
                "is_active": True,
                "is_auto": True,
            },
        )

    # 💪 Workout → Routine
    for w in workouts:
        title = f"Workout – {w.title or w.day}"
        # default workout time suggestion
        start_time, end_time = time(5, 30), time(6, 0)
        DailyRoutine.objects.update_or_create(
            user=user,
            title=title,
            start_time=start_time,
            end_time=end_time,
            defaults={
                "description": (w.exercises or "")[:150],
                "days": [w.day],
                "is_active": True,
                "is_auto": True,
            },
        )

    # 🧹 Optional cleanup: remove old auto-generated routines
    linked_titles = (
        list(diet_plans.values_list("meal_time", flat=True))
        + [f"Workout – {w.title or w.day}" for w in workouts]
    )
    DailyRoutine.objects.filter(user=user, is_auto=True).exclude(title__in=linked_titles).delete()

def suggest_meal_time(meal_name):
    """Returns default time slots for each meal"""
    mapping = {
        "Waking Snack": (time(4,50), time(5,0)),
        "Pre-workout Snack": (time(5,0), time(5,30)),
        "Post-workout snack": (time(6,30), time(6,45)),
        "Breakfast": (time(8,15), time(8,45)),
        "Lunch": (time(13,30), time(14,0)),
        "Evening Snack": (time(16,45), time(17,0)),
        "Dinner": (time(20,30), time(21,0)),
        "Before Bed": (time(21,30), time(22,0)),
    }
    return mapping.get(meal_name, (time(12,0), time(12,30)))

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
    user = request.user
    weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    meal_times = [
        "Waking Snack", 
        "Breakfast", "Mid-Morning", "Lunch", "Evening Snack","Pre-workout Snack", "Post-workout snack", "Dinner", "Before Bed"
    ]

    if request.method == "POST":
        for day in weekdays:
            for meal in meal_times:
                meal_slug = f"{day.lower().replace(' ', '-')}_{meal.lower().replace(' ', '-')}"
                # ✅ Handles [] suffix correctly
                foods = [f.strip() for f in request.POST.getlist(f"{meal_slug}[]") if f.strip()]

                if foods:
                    DietPlan.objects.update_or_create(
                        user=user,
                        day=day,
                        meal_time=meal,
                        defaults={"food_items": "\n".join(foods)}
                    )

        messages.success(request, "✅ Weekly diet plan saved successfully!")
        return redirect("diet_setup")

    # Load data
    diet_data = []
    for day in weekdays:
        entries = DietPlan.objects.filter(user=user, day=day)
        day_meals = {}
        for meal in meal_times:
            obj = entries.filter(meal_time=meal).first()
            day_meals[meal] = obj.food_items if obj else ""
        diet_data.append((day, day_meals.items()))

    return render(request, "diet_setup.html", {"diet_data": diet_data})

@login_required
def delete_diet_item(request):
    if request.method == "POST":
        user = request.user
        day = request.POST.get("day")
        meal_time = request.POST.get("meal_time")
        food_item = request.POST.get("food_item")

        entry = DietPlan.objects.filter(user=user, day=day, meal_time=meal_time).first()

        if entry:
            lines = entry.food_items.split("\n")
            new_lines = [l for l in lines if l.strip() != food_item.strip()]

            entry.food_items = "\n".join(new_lines)
            entry.save()

            return JsonResponse({"success": True})

    return JsonResponse({"success": False, "error": "Invalid request"})

@login_required
def update_diet_item(request):
    """AJAX edit: update a single food item inline."""
    if request.method == "POST":
        meal_time = request.POST.get("meal_time")
        old_food = request.POST.get("old_food")
        new_food = request.POST.get("new_food")

        plan = DietPlan.objects.filter(user=request.user, meal_time=meal_time).first()
        if not plan:
            return JsonResponse({"success": False, "error": "Meal not found"})

        foods = [f.strip() for f in plan.food_items.splitlines() if f.strip()]
        if old_food in foods:
            foods[foods.index(old_food)] = new_food
            plan.food_items = "\n".join(foods)
            plan.save()
            return JsonResponse({"success": True})
        return JsonResponse({"success": False, "error": "Old food not found"})

    return JsonResponse({"success": False, "error": "Invalid request"})

from django.http import JsonResponse

@login_required
def workout_setup(request):
    profile = UserProfile.objects.filter(user=request.user).first()
    if not profile or not profile.height_cm or not profile.current_weight:
        messages.info(request, "Complete your profile first.")
        return redirect('profile')

    weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

    if request.method == 'POST':
        # Delete and recreate to simplify saving
        WorkoutPlan.objects.filter(user=request.user).delete()
        for day in weekdays:
            slugified = slugify(day)
            title_field = f"{slugified}_title"
            exercise_list = request.POST.getlist(slugified)
            clean_list = [e.strip() for e in exercise_list if e.strip()]
            title_value = request.POST.get(title_field, "").strip()

            if clean_list or title_value:
                WorkoutPlan.objects.create(
                    user=request.user,
                    day=day,
                    title=title_value or f"{day} Workout",
                    exercises="\n".join(clean_list)
                )

        messages.success(request, "✅ Workout plan updated successfully!")
        return redirect('dashboard')

    # Fetch existing workouts and format them
    existing = WorkoutPlan.objects.filter(user=request.user)
    existing_data = []
    for day in weekdays:
        record = next((e for e in existing if e.day == day), None)
        title = record.title if record else ''
        exercises = [e.strip() for e in (record.exercises.splitlines() if record else []) if e.strip()]
        existing_data.append((day, title, exercises))

    return render(request, 'workout_setup.html', {
        'workout_data': existing_data
    })

@login_required
def delete_workout_item(request):
    """AJAX delete for a single exercise from WorkoutPlan."""
    if request.method == "POST":
        day = request.POST.get("day")
        exercise = request.POST.get("exercise")

        if not day or not exercise:
            return JsonResponse({"success": False, "error": "Missing data"})

        # Find the matching record for the user and day
        plan = WorkoutPlan.objects.filter(user=request.user, day=day).first()
        if not plan:
            return JsonResponse({"success": False, "error": "Workout plan not found for this day."})

        exercises = [e.strip() for e in plan.exercises.splitlines() if e.strip()]
        if exercise in exercises:
            exercises.remove(exercise)
            plan.exercises = "\n".join(exercises)
            plan.save()
            return JsonResponse({"success": True})
        else:
            return JsonResponse({"success": False, "error": "Exercise not found."})

    return JsonResponse({"success": False, "error": "Invalid request"})

@login_required
def dashboard(request):
    user = request.user
    # Ensure profile exists
    profile, created = UserProfile.objects.get_or_create(user=user)
    if not profile.height_cm or not profile.current_weight:
        messages.info(request, "⚠️ Your profile is incomplete. Add details for better tracking.")
        return redirect('profile')

    # Checks if setup exists
    diet_exists = DietPlan.objects.filter(user=user).exists()
    water_exists = WaterTarget.objects.filter(user=user).exists()
    workout_exists = WorkoutPlan.objects.filter(user=user).exists()

    if not diet_exists:
        messages.warning(request, "⚠️ You haven’t added your diet plan yet.")
    if not water_exists:
        messages.warning(request, "⚠️ You haven’t set your water intake goal yet.")
    if not workout_exists:
        messages.warning(request, "⚠️ You haven’t created a workout plan yet.")

    today = timezone.localdate()
    weekday = today.strftime('%A')

    # ⭐ Fetch today's plans
    diet_qs = DietPlan.objects.filter(user=user, day=weekday)
    workout_qs = WorkoutPlan.objects.filter(user=user, day=weekday)

    # Daily progress
    progress, _ = DailyProgress.objects.get_or_create(user=user, date=today)

    # 💧 Water target
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

    # Handle POST - save progress
    if request.method == "POST":
        # weight = request.POST.get("today_weight")
        # if weight:
        #     progress.today_weight = Decimal(weight)
        #     WeightEntry.objects.update_or_create(
        #         user=user, date=today, defaults={"weight": Decimal(weight)}
        #     )

        # Save food checkboxes
        selected_foods = [
            v for k, v in request.POST.items()
            if k.startswith("food_")
        ]
        progress.completed_foods = selected_foods

        # Save workouts
        completed_workouts = [
            v for k, v in request.POST.items() if k.startswith("workout_")
        ]
        progress.completed_workouts = completed_workouts

        # Save water
        completed_water = [
            i for i in range(1, total_units + 1)
            if f"water_{i}" in request.POST
        ]
        progress.water_glasses = completed_water

        # Save completed routines
        completed_routines = [
            r.title for r in DailyRoutine.objects.filter(user=user, is_active=True)
            if f"routine_{r.id}" in request.POST
        ]
        progress.completed_routines = completed_routines

        progress.save()
        messages.success(request, "✅ Progress saved successfully!")
        return redirect("dashboard")

    # 🥗 Prepare Diet for template
    meal_order = [
        "Waking Snack", 
        "Breakfast", "Mid-Morning", "Lunch", "Evening Snack","Pre-workout Snack", "Post-workout snack", "Dinner", "Before Bed"
    ]

    diet_unsorted = {
        d.meal_time: [i.strip() for i in d.food_items.splitlines() if i.strip()]
        for d in diet_qs
    }

    diet = {meal: diet_unsorted.get(meal, []) for meal in meal_order if meal in diet_unsorted}

    # 🏋️ Prepare workouts for template
    workouts = []
    if workout_qs.exists():
        workouts = [
            w.strip() for w in workout_qs.first().exercises.splitlines()
        ]

    # 🕒 Build time-based daily flow (NEW)
    meal_times = [
        "Waking Snack", 
        "Breakfast", "Mid-Morning", "Lunch", "Evening Snack","Pre-workout Snack", "Post-workout snack", "Dinner", "Before Bed"
    ]
    time_mapping = {
        "Waking Snack": time(5, 0),
        "Breakfast": time(7, 0),
        "Mid-Morning": time(10, 0),
        "Lunch": time(12, 30),
        "Evening Snack": time(15, 45),
        "Pre-workout Snack": time(17, 0),
        "Post-workout snack": time(19, 30),
        "Dinner": time(20, 30),
        "Before Bed": time(21, 30),
    }

    ordered_diet = []
    for meal in meal_times:
        entry = diet_qs.filter(meal_time=meal).first()
        if entry:
            ordered_diet.append({
                "meal_time": meal,
                "foods": [f.strip() for f in entry.food_items.splitlines() if f.strip()],
                "time": time_mapping.get(meal),
            })

    workout_entry = workout_qs.first() if workout_qs.exists() else None
    workout_data = None
    if workout_entry:
        workout_data = {
            "title": f"Workout – {workout_entry.title or 'Session'}",
            "exercises": [x.strip() for x in workout_entry.exercises.splitlines() if x.strip()],
            "time": time(5, 30),
        }

    timeline = []
    for meal in ordered_diet:
        timeline.append({
            "type": "meal",
            "title": meal["meal_time"],
            "items": meal["foods"],
            "time": meal["time"],
            "icon": "🍽️",
        })

    if workout_data:
        timeline.append({
            "type": "workout",
            "title": workout_data["title"],
            "items": workout_data["exercises"],
            "time": workout_data["time"],
            "icon": "🏋️",
        })

    timeline.sort(key=lambda x: x["time"])
    for t in timeline:
        t["time_label"] = t["time"].strftime("%I:%M %p")

    # ✅ Calculate progress %
    total_items = (
        len(workouts)
        + sum(len(v) for v in diet.values())
        + total_units
    )
    completed_items = (
        len(progress.completed_workouts or [])
        + len(progress.completed_foods or [])
        + len(progress.water_glasses or [])
        + len(progress.completed_routines or [])
    )
    progress_percent = int((completed_items / total_items) * 100) if total_items else 0

    # 📈 Weight chart
    recent_weights = list(WeightEntry.objects.filter(user=user).order_by('-date')[:7])[::-1]
    weights = [float(w.weight) for w in recent_weights]
    labels = [w.date.strftime("%d %b") for w in recent_weights]
    weight_diff = (
        round(float(recent_weights[-1].weight) - float(recent_weights[-2].weight), 1)
        if len(recent_weights) >= 2 else 0
    )

    # 💬 Motivation
    bmi = profile.bmi
    if not progress.today_weight:
        motivation = "🏁 Start by adding today’s weight to see your BMI and progress."
    elif bmi:
        if bmi < 18.5:
            motivation = "You're underweight. Let’s build strength! 💪"
        elif 18.5 <= bmi < 25:
            motivation = "Healthy range! Keep it up! 🥗"
        elif 25 <= bmi < 30:
            motivation = "Slightly overweight. Let's trim it down! 🏃"
        else:
            motivation = "Obese category. Take care of your health. ❤️"
    else:
        motivation = "📊 Add your height and weight to calculate BMI."

    user_height = profile.height_cm
    yesterday_weight = weights[-2] if len(weights) >= 2 else None

    # 🕓 Routines (manual)
    tz = pytz.timezone(getattr(settings, "TIME_ZONE", "Asia/Kolkata"))
    now = timezone.now().astimezone(tz)
    today = timezone.localdate()
    weekday = today.strftime('%A')

    all_routines = DailyRoutine.objects.filter(
        user=request.user,
        is_active=True,
        is_auto=False
    )
    routines = sorted(
        [r for r in all_routines if weekday in (r.days or [])],
        key=lambda r: r.start_time
    )

    today_routines = []
    for r in routines:
        start_ts = datetime.combine(today, r.start_time)
        is_done = r.title in (progress.completed_routines or [])
        today_routines.append({
            "id": r.id,
            "title": r.title,
            "time": f"{r.start_time.strftime('%I:%M %p')} - {r.end_time.strftime('%I:%M %p')} (IST)",
            "description": r.description or "",
            "start_ts": int(tz.localize(start_ts).timestamp() * 1000),
            "is_done": is_done,
        })

    now = timezone.localtime().astimezone(tz)
    next_routine = None
    for r in routines:
        start_dt = tz.localize(datetime.combine(today, r.start_time))
        if start_dt > now:
            next_routine = r
            break

    next_routine_summary = None
    if next_routine:
        start_dt = tz.localize(datetime.combine(today, next_routine.start_time))
        next_routine_summary = {
            "title": next_routine.title,
            "time": f"{next_routine.start_time.strftime('%I:%M %p')} - {next_routine.end_time.strftime('%I:%M %p')} (IST)",
            "start_ts": int(start_dt.timestamp() * 1000)
        }

    # 🎯 Final context
    context = {
        'today': today,
        'diet': diet or {},
        'workouts': workouts or [],
        'timeline': timeline or [],  # 👈 new daily flow
        'progress': progress or {},
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
        'today_routines': today_routines or [],
        'timezone': str(tz),
        'next_routine_summary': next_routine_summary,
    }

    return render(request, 'dashboard.html', context)

# new feature

# | Body Part       | Expected Change                          |
# | --------------- | ---------------------------------------- |
# | Weight          | +0.25 to +0.6 kg/week                    |
# | Hips            | +0.5 to +1.5 cm/month                    |
# | Glutes          | +1 to +3 cm/month                        |
# | Thighs (middle) | +0.5 to +1.5 cm/month                    |
# | Arms (flexed)   | +0.3 to +1 cm/month                      |
# | Waist           | +0 to +1 cm/month (small gain is normal) |
# | Shoulders       | +0.5 to +1.5 cm/month                    |

@login_required
def analysis(request):
    user = request.user
    today = date.today()
    range_option = request.GET.get("range", "week")
    selected_range = range_option

    # 🗓 Determine range
    if range_option == "day":
        start_date, end_date = today, today
    elif range_option == "week":
        start_date, end_date = today - timedelta(days=today.weekday()), today
    elif range_option == "month":
        start_date, end_date = today.replace(day=1), today
    elif range_option == "year":
        start_date, end_date = today.replace(month=1, day=1), today
    else:
        first = WeightEntry.objects.filter(user=user).first()
        start_date, end_date = (first.date if first else today), today

    # 📊 Collect entries
    progress_entries = DailyProgress.objects.filter(user=user, date__range=[start_date, end_date]).order_by("date")
    total_days = (end_date - start_date).days + 1

    # 🍽, 💪, 💧 summary
    meal_completed_days = sum(1 for e in progress_entries if e.meals_completed)
    workout_days = sum(1 for e in progress_entries if e.completed_workouts)
    routine_days = sum(1 for e in progress_entries if e.completed_routines)

    water_data, water_labels = [], []
    for i in range(total_days):
        d = start_date + timedelta(days=i)
        entry = next((e for e in progress_entries if e.date == d), None)
        water_data.append(len(entry.water_glasses) if entry else 0)
        water_labels.append(d.strftime("%d %b"))

    meal_percent = int((meal_completed_days / total_days) * 100) if total_days else 0
    workout_percent = int((workout_days / total_days) * 100) if total_days else 0
    routine_percent = int((routine_days / total_days) * 100) if total_days else 0
    avg_water = round(sum(water_data) / total_days, 1) if total_days else 0

    # ⚖️ Weight
    weight_entries = WeightEntry.objects.filter(user=user, date__range=[start_date, end_date]).order_by("date")
    weight_labels = [w.date.strftime("%d %b") for w in weight_entries]
    weight_values = [float(w.weight) for w in weight_entries]
    weight_change = round(weight_entries.last().weight - weight_entries.first().weight, 1) if weight_entries.count() >= 2 else 0

    # 📈 Dynamic Insights
    insights = []

    # 🥗 Meal Insight
    if meal_percent >= 90:
        insights.append("🍽️ Excellent consistency with meals! Keep fueling right.")
    elif meal_percent >= 70:
        insights.append("🥗 Great job! You're eating healthy most days.")
    elif meal_percent > 0:
        insights.append("⚠️ Meal tracking could improve — try to log meals more consistently.")
    else:
        insights.append("🍴 No meal logs found for this period.")

    # 🏋 Workout Insight
    if workout_percent >= 80:
        insights.append("💪 You’re crushing your workouts — awesome consistency!")
    elif workout_percent >= 50:
        insights.append("🏃 Good effort! Try to increase workout days for even better results.")
    elif workout_percent > 0:
        insights.append("😅 You worked out a few times. Let’s aim for more consistency next week!")
    else:
        insights.append("🛋️ No workouts logged. Let's get moving!")

    # 💧 Water Insight
    if avg_water >= 10:
        insights.append("💧 Hydration hero! You’re meeting your water goals daily.")
    elif avg_water >= 6:
        insights.append("🚰 Decent hydration — drink a little more to reach your target.")
    elif avg_water > 0:
        insights.append("🥵 You might be underhydrated — aim for more water per day.")
    else:
        insights.append("🚱 No water intake logged.")

    # ⚖️ Weight Insight
    if weight_change > 0:
        insights.append(f"📈 You’ve gained {weight_change} kg — great if bulking, watch diet otherwise.")
    elif weight_change < 0:
        insights.append(f"📉 You’ve lost {abs(weight_change)} kg — keep up the momentum!")
    else:
        insights.append("⚖️ Weight stable — consistency is key!")

    # ❤️ Overall Motivation
    if meal_percent + workout_percent + routine_percent > 220:
        insights.append("🔥 You’re performing like a champion! Keep up this level.")
    elif meal_percent + workout_percent + routine_percent > 150:
        insights.append("🌟 Great progress! You’re building strong habits.")
    elif meal_percent + workout_percent + routine_percent > 80:
        insights.append("💡 You’re on the right track — consistency will bring results.")
    else:
        insights.append("🚀 Let’s push a bit more next week!")

    context = {
        'selected_range': selected_range,
        'meal_completion_percent': meal_percent,
        'workout_completion_percent': workout_percent,
        'routine_completion_percent': routine_percent,
        'meal_completed_days': meal_completed_days,
        'workout_days': workout_days,
        'routine_completed_days': routine_days,
        'total_days': total_days,
        'average_water': avg_water,
        'water_goal_glasses': 12,
        'water_goal_liters': round(12 * 250 / 1000, 1),
        'water_chart': {'labels': json.dumps(water_labels), 'data': json.dumps(water_data)},
        'weight_chart': {'labels': json.dumps(weight_labels), 'data': json.dumps(weight_values)},
        'first_weight': weight_entries.first().weight if weight_entries else 'N/A',
        'last_weight': weight_entries.last().weight if weight_entries else 'N/A',
        'weight_change': weight_change,
        'insights': insights,
    }
    return render(request, 'analysis.html', context)

@login_required
def profile(request):
    user = request.user
    profile, created = UserProfile.objects.get_or_create(user=user)

    if request.method == 'POST':
        profile.full_name = request.POST.get('full_name') or user.username
        
        birth_date = request.POST.get('birth_date')  # ✅ NEW
        if birth_date:
            profile.birth_date = birth_date

        profile.sex = request.POST.get('sex')
        profile.height_cm = request.POST.get('height_cm')
        profile.current_weight = request.POST.get('current_weight')

        profile.save()
        messages.success(request, "✅ Profile updated.")
        return redirect('diet_setup')

    return render(request, 'profile.html', {
        'profile': profile,
    })

import json
@login_required
def routine_setup(request):
    weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

    # 🧾 Handle POST — Save routine
    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        start_time = request.POST.get("start_time")
        end_time = request.POST.get("end_time")
        days = request.POST.getlist("days")
        description = request.POST.get("description")
        # Ensure required fields are present
        if not title or not start_time or not end_time or not days:
            messages.error(request, "⚠️ Please fill all required fields.")
            return redirect("routine_setup")

        try:
            DailyRoutine.objects.create(
                user=request.user,
                title=title,
                start_time=start_time,
                end_time=end_time,
                days=days,  # Stored as JSON
                description=description,
            )
            messages.success(request, "✅ Routine saved successfully!")
        except Exception as e:
            messages.error(request, f"❌ Error saving routine: {e}")

        return redirect("routine_setup")

    # Fetch only user routines
    routines = DailyRoutine.objects.filter(user=request.user, is_auto=False).order_by("start_time")

    return render(request, "routine_setup.html", {
        "weekdays": weekdays,
        "routines": routines,
    })

@login_required
def edit_routine(request, routine_id):
    if request.method == "POST":
        try:
            routine = DailyRoutine.objects.get(id=routine_id, user=request.user)
        except DailyRoutine.DoesNotExist:
            messages.error(request, "⚠️ Routine not found or cannot be edited.")
            return redirect("routine_setup")

        routine.title = request.POST.get("title")
        routine.start_time = request.POST.get("start_time")
        routine.end_time = request.POST.get("end_time")
        routine.days = request.POST.getlist("days")
        routine.description = request.POST.get("description")

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

