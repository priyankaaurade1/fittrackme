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

    weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    meal_times = [
        "Waking Snack", "Pre-workout Snack", "Post-workout snack","Breakfast", "Lunch",
        "Evening Snack", "Dinner", "Before Bed"
    ]
    selected_day = request.GET.get("day", "Monday")  # Default to Monday

    if request.method == 'POST':
        selected_day = request.POST.get("day", "Monday")
        DietPlan.objects.filter(user=request.user, day=selected_day).delete()
        for meal in meal_times:
            meal_slug = meal.lower().replace(' ', '-')
            food_items = []
            for key, value in request.POST.items():
                if key.startswith(f"{meal_slug}_item_") and value.strip():
                    food_items.append(value.strip())
            if food_items:
                DietPlan.objects.create(
                    user=request.user,
                    day=selected_day,
                    meal_time=meal,
                    food_items="\n".join(food_items)
                )
        messages.success(request, f"Diet plan updated for {selected_day}! 🍽️")
        return redirect(f"{request.path}?day={selected_day}")

    # Fetch existing meals for selected day
    existing = DietPlan.objects.filter(user=request.user, day=selected_day)
    meal_data = []
    for meal in meal_times:
        match = next((e.food_items for e in existing if e.meal_time == meal), '')
        meal_data.append((meal, match))

    return render(request, 'diet_setup.html', {
        'meal_data': meal_data,
        'weekdays': weekdays,
        'selected_day': selected_day,
    })

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
def delete_diet_item(request):
    """AJAX delete for a single food item in DietPlan."""
    if request.method == "POST":
        meal_time = request.POST.get("meal_time")
        food_item = request.POST.get("food_item")

        if not meal_time or not food_item:
            return JsonResponse({"success": False, "error": "Missing data"})

        # Find the matching record
        diet = DietPlan.objects.filter(user=request.user, meal_time=meal_time).first()
        if not diet:
            return JsonResponse({"success": False, "error": "Meal not found"})

        # Remove the food item from the text list
        foods = [f.strip() for f in diet.food_items.splitlines() if f.strip()]
        if food_item in foods:
            foods.remove(food_item)
            diet.food_items = "\n".join(foods)
            diet.save()
            return JsonResponse({"success": True})
        else:
            return JsonResponse({"success": False, "error": "Food not found in list"})

    return JsonResponse({"success": False, "error": "Invalid request"})

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

    # ✅ Ensure profile exists
    profile, created = UserProfile.objects.get_or_create(user=user)
    if not profile.height_cm or not profile.current_weight:
        messages.info(request, "Please complete your profile setup first.")
        return redirect('profile')

    # ⚙️ Allow dashboard to load even if setup is incomplete
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

    # ✅ Query user data
    diet_qs = DietPlan.objects.filter(user=user) if diet_exists else []
    workout_qs = WorkoutPlan.objects.filter(user=user, day=weekday) if workout_exists else []
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

    # ✅ Timezone-safe routine handling
    tz = pytz.timezone(getattr(settings, "TIME_ZONE", "Asia/Kolkata"))
    now = timezone.now().astimezone(tz)
    today = timezone.localdate()
    weekday = today.strftime('%A')

    all_routines = DailyRoutine.objects.filter(user=user, is_active=True).order_by('start_time')
    routines = [r for r in all_routines if weekday in (r.days or [])]

    today_routines = []
    next_routine = None
    next_diff = float('inf')

    for r in routines:
        # compute server-side aware datetime for the start_time
        routine_dt = datetime.combine(today, r.start_time)
        routine_dt = timezone.make_aware(routine_dt, tz)
        now_local = timezone.localtime(timezone.now(), tz)
        diff_seconds = int((routine_dt - now_local).total_seconds())

        # status: store None / "it's time" / positive seconds (not minutes)
        if diff_seconds > 0:
            status = diff_seconds  # seconds left (absolute)
            if diff_seconds < next_diff:
                next_diff = diff_seconds
                next_routine = r
        elif -30 * 60 <= diff_seconds <= 0:
            status = "⏰ It's time!"
        else:
            status = None

        today_routines.append({
            "id": r.id,
            "title": r.title,
            "time": f"{r.start_time.strftime('%I:%M %p')} - {r.end_time.strftime('%I:%M %p')}",
            "description": r.description,
            # pass absolute timestamp in milliseconds for client-side calculations
            "start_ts": int(routine_dt.timestamp() * 1000),
            "status": status,
            "is_done": r.title in (progress.completed_routines or [])
        })

    # Next upcoming summary (pass start_ts as well)
    next_routine_summary = None
    if next_routine:
        next_time_str = f"{next_routine.start_time.strftime('%I:%M %p')} - {next_routine.end_time.strftime('%I:%M %p')}"
        next_routine_summary = {
            "title": next_routine.title,
            "time": next_time_str,
            "start_ts": int(datetime.combine(today, next_routine.start_time).astimezone(tz).timestamp() * 1000),
            "desc": next_routine.description or ""
        }
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
        'today_routines': today_routines,
        'next_routine_summary': next_routine_summary,
    }

    return render(request, 'dashboard.html', context)

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
    weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

    if request.method == "POST":
        title = request.POST.get("title")
        description = request.POST.get("description")
        start_time = request.POST.get("start_time")
        end_time = request.POST.get("end_time")
        days = request.POST.getlist("days")

        if not title or not start_time or not end_time or not days:
            messages.error(request, "⚠️ Please fill all fields and select at least one day.")
            return redirect("routine_setup")

        DailyRoutine.objects.create(
            user=request.user,
            title=title,
            description=description,
            start_time=start_time,
            end_time=end_time,
            days=days
        )
        messages.success(request, "✅ Routine added successfully!")
        return redirect("routine_setup")

    routines = DailyRoutine.objects.filter(user=request.user).order_by("start_time")
    return render(request, "routine_setup.html", {
        "routines": routines,
        "weekdays": weekdays
    })

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

