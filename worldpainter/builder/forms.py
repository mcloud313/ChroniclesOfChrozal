#worldpainter/builder/forms.py
from django import forms
from .models import Rooms

# A list of the cardinal and ordinal directions for exits
EXIT_DIRECTIONS = [
    "north", "south", "east", "west", "up", "down",
    "northeast", "northwest", "southeast", "southwest"
]

class RoomAdminForm(forms.ModelForm):
    """A custom form for creating and editing Rooms in the Django admin."""
    
    # ... (the 10 direction_exit fields are the same as before)
    north_exit = forms.ModelChoiceField(queryset=Rooms.objects.none(), required=False)
    south_exit = forms.ModelChoiceField(queryset=Rooms.objects.none(), required=False)
    east_exit = forms.ModelChoiceField(queryset=Rooms.objects.none(), required=False)
    west_exit = forms.ModelChoiceField(queryset=Rooms.objects.none(), required=False)
    up_exit = forms.ModelChoiceField(queryset=Rooms.objects.none(), required=False)
    down_exit = forms.ModelChoiceField(queryset=Rooms.objects.none(), required=False)
    northeast_exit = forms.ModelChoiceField(queryset=Rooms.objects.none(), required=False)
    northwest_exit = forms.ModelChoiceField(queryset=Rooms.objects.none(), required=False)
    southeast_exit = forms.ModelChoiceField(queryset=Rooms.objects.none(), required=False)
    southwest_exit = forms.ModelChoiceField(queryset=Rooms.objects.none(), required=False)

    def __init__(self, *args, **kwargs):
        """
        This special method runs when the form is created.
        We use it to dynamically filter the exit dropdowns.
        """
        super().__init__(*args, **kwargs)
        
        # 'instance' is the Room object being edited.
        room_instance = self.instance
        
        if room_instance and room_instance.area:
            # Create a queryset of rooms that are only in the same area.
            qs = Rooms.objects.filter(area=room_instance.area)
            
            # Apply this filtered queryset to all of our exit fields.
            for direction in EXIT_DIRECTIONS:
                field_name = f'{direction}_exit'
                self.fields[field_name].queryset = qs
    
    class Meta:
        model = Rooms
        fields = '__all__'
        exclude = ['exits']