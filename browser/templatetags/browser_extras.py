from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """Permite acceder a un dict por clave dinámica en templates."""
    return dictionary.get(key, "")
