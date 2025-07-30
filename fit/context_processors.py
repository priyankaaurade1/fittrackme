from .models import UserProfile

def user_profile(request):
    if request.user.is_authenticated:
        try:
            profile = UserProfile.objects.get(user=request.user)
            return {'user_full_name': profile.full_name}
        except UserProfile.DoesNotExist:
            return {'user_full_name': request.user.username}
    return {}
