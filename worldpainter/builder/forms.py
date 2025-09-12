#worldpainter/builder/forms.py
from django import forms
from .models import Rooms

# A list of the cardinal and ordinal directions for exits
EXIT_DIRECTIONS = [
    "north", "south", "east", "west", "up", "down",
    "northeast", "northwest", "southeast", "southwest"
]

class RoomAdminForm(forms.ModelForm):
    """A custom form for creating and editing rooms in the Djangi Admin"""

    # Create a dropdown field for each possible exit direction.
    # `required=False` means the exit is optional
    # `queryset` tells Django to fill the dropdown with all Room objects
    north_exit = forms.ModelChoiceField(queryset=Rooms.objects.all(), required=False)
    south_exit = forms.ModelChoiceField(queryset=Rooms.objects.all(), required=False)
    east_exit = forms.ModelChoiceField(queryset=Rooms.objects.all(), required=False)
    west_exit = forms.ModelChoiceField(queryset=Rooms.objects.all(), required=False)
    up_exit = forms.ModelChoiceField(queryset=Rooms.objects.all(), required=False)
    down_exit = forms.ModelChoiceField(queryset=Rooms.objects.all(), required=False)
    northeast_exit = forms.ModelChoiceField(queryset=Rooms.objects.all(), required=False)
    northwest_exit = forms.ModelChoiceField(queryset=Rooms.objects.all(), required=False)
    southeast_exit = forms.ModelChoiceField(queryset=Rooms.objects.all(), required=False)
    southwest_exit = forms.ModelChoiceField(queryset=Rooms.objects.all(), required=False)

    class Meta:
        model = Rooms
        # We will use all fields from the Room model...
        fields = '__all__'
        # ...except for the raw 'exits' JSON field, which we are replacing.
        exclude = ['exits']