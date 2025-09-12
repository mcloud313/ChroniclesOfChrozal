#worldpainter/builder/forms.py
from django import forms
from .models import Rooms
from .models import Rooms, MobTemplates, ItemTemplates 

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

    spawner_mob_1 = forms.ModelChoiceField(queryset=MobTemplates.objects.all(), required=False, label="Spawner 1: Mob")
    spawner_count_1 = forms.IntegerField(required=False, label="Max Present", min_value=1)

    spawner_mob_2 = forms.ModelChoiceField(queryset=MobTemplates.objects.all(), required=False, label="Spawner 2: Mob")
    spawner_count_2 = forms.IntegerField(required=False, label="Max Present", min_value=1)
    
    spawner_mob_3 = forms.ModelChoiceField(queryset=MobTemplates.objects.all(), required=False, label="Spawner 3: Mob")
    spawner_count_3 = forms.IntegerField(required=False, label="Max Present", min_value=1)

    spawner_mob_4 = forms.ModelChoiceField(queryset=MobTemplates.objects.all(), required=False, label="Spawner 4: Mob")
    spawner_count_4 = forms.IntegerField(required=False, label="Max Present", min_value=1)

    spawner_mob_5 = forms.ModelChoiceField(queryset=MobTemplates.objects.all(), required=False, label="Spawner 5: Mob")
    spawner_count_5 = forms.IntegerField(required=False, label="Max Present", min_value=1)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        room_instance = self.instance
        
        if room_instance and room_instance.pk: # Check if this is an existing room
            # --- Exit filtering logic (unchanged) ---
            if room_instance.area:
                qs = Rooms.objects.filter(area=room_instance.area)
                for direction in EXIT_DIRECTIONS:
                    self.fields[f'{direction}_exit'].queryset = qs

            # --- NEW: Populate form with existing spawner data ---
            if isinstance(room_instance.spawners, dict):
                for i, (mob_id, spawn_info) in enumerate(room_instance.spawners.items(), 1):
                    if i > 5: break # Stop if there are more than 5 spawners
                    try:
                        self.initial[f'spawner_mob_{i}'] = int(mob_id)
                        self.initial[f'spawner_count_{i}'] = spawn_info.get('max_present')
                    except (ValueError, TypeError):
                        continue # Skip if data is malformed

    class Meta:
        model = Rooms
        fields = '__all__'
        # Exclude both raw JSON fields
        exclude = ['exits', 'spawners']

class MobTemplateAdminForm(forms.ModelForm):
    """A custom form for creating and editing Mob Templates."""
    
    # Field for the maximum coinage this mob can drop
    loot_coinage_max = forms.IntegerField(required=False, label="Max Coinage Drop")

    # --- Create fields for up to 5 potential item drops ---
    loot_item_1 = forms.ModelChoiceField(queryset=ItemTemplates.objects.all(), required=False, label="Loot Item 1")
    loot_chance_1 = forms.FloatField(required=False, label="Chance (0.0 to 1.0)", min_value=0.0, max_value=1.0)

    loot_item_2 = forms.ModelChoiceField(queryset=ItemTemplates.objects.all(), required=False, label="Loot Item 2")
    loot_chance_2 = forms.FloatField(required=False, label="Chance (0.0 to 1.0)", min_value=0.0, max_value=1.0)

    loot_item_3 = forms.ModelChoiceField(queryset=ItemTemplates.objects.all(), required=False, label="Loot Item 3")
    loot_chance_3 = forms.FloatField(required=False, label="Chance (0.0 to 1.0)", min_value=0.0, max_value=1.0)

    loot_item_4 = forms.ModelChoiceField(queryset=ItemTemplates.objects.all(), required=False, label="Loot Item 4")
    loot_chance_4 = forms.FloatField(required=False, label="Chance (0.0 to 1.0)", min_value=0.0, max_value=1.0)

    loot_item_5 = forms.ModelChoiceField(queryset=ItemTemplates.objects.all(), required=False, label="Loot Item 5")
    loot_chance_5 = forms.FloatField(required=False, label="Chance (0.0 to 1.0)", min_value=0.0, max_value=1.0)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # If we are editing an existing mob, populate the form with its loot data
        mob_instance = self.instance
        if mob_instance and mob_instance.pk and isinstance(mob_instance.loot, dict):
            self.initial['loot_coinage_max'] = mob_instance.loot.get('coinage_max')
            
            item_drops = mob_instance.loot.get('items', [])
            for i, item_drop in enumerate(item_drops, 1):
                if i > 5: break
                self.initial[f'loot_item_{i}'] = item_drop.get('template_id')
                self.initial[f'loot_chance_{i}'] = item_drop.get('chance')

    class Meta:
        model = MobTemplates
        fields = '__all__'
        # Exclude the raw JSON fields we are replacing
        exclude = ['loot', 'attacks', 'flags', 'stats', 'variance']