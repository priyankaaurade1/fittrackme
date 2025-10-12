from django import template

register = template.Library()

@register.filter
def first_name(value):
    if not value:
        return ""
    parts = value.strip().split()
    # Skip honorifics like 'Dr.', 'Mr.', etc.
    if parts[0].lower().replace('.', '') in ['mr', 'mrs', 'ms', 'dr']:
        return parts[1] if len(parts) > 1 else parts[0]
    return parts[0]
