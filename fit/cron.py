# from django.utils import timezone
# from .models import DailyRoutine
# from django.core.mail import send_mail
# from datetime import datetime

# def send_routine_notifications():
#     now = timezone.localtime()
#     current_time = now.strftime("%H:%M")

#     routines = DailyRoutine.objects.filter(time=current_time, is_active=True)
#     for routine in routines:
#         send_mail(
#             subject=f"⏰ Reminder: {routine.title}",
#             message=f"Hey {routine.user.username}, it's time for: {routine.title}\n\n{routine.description or ''}",
#             from_email="fittrackme@yourdomain.com",
#             recipient_list=[routine.user.email],
#             fail_silently=True,
#         )
