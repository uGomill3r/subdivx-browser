import os

from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """Permite acceder a un dict por clave dinámica en templates."""
    return dictionary.get(key, "")


@register.filter
def splitext(filename):
    """Quita la extensión de un nombre de archivo (.mp4, .mkv, etc.)."""
    if not filename:
        return filename
    return os.path.splitext(filename)[0]
