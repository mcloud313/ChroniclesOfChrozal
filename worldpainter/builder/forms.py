#worldpainter/builder/forms.py
from django import forms
from .models import Rooms
from .models import Rooms, MobTemplates, ItemTemplates, Areas, DamageTypes

# A list of the cardinal and ordinal directions for exits
# A list of the cardinal and ordinal directions for exits
EXIT_DIRECTIONS = [
    "north", "south", "east", "west", "up", "down",
    "northeast", "northwest", "southeast", "southwest"
]

MOB_FLAG_CHOICES = [
    ('AGGRESSIVE', 'Aggressive'),
    ('SENTINEL', 'Sentinel (Does not move)'),
    ('SCAVENGER', 'Scavenger (Picks up items)'),
    ('HELPER', 'Helper (Assists other mobs)'),
]

STAT_NAMES = ["might", "vitality", "agility", "intellect", "aura", "persona"]

def get_damage_type_choices():
    """Gets a list of all damage types from the database."""
    # This check is to prevent errors when running initial migrations before the table exists.
    try:
        return [dt.name for dt in DamageTypes.objects.all().order_by('name')]
    except Exception:
        return []
    
DAMAGE_TYPES = get_damage_type_choices()

class RoomAdminForm(forms.ModelForm):
    """A custom form for creating and editing Rooms in the Django admin."""
    
    # Initialize the fields to be empty. We will populate them dynamically.
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
    spawner_mob_2 = forms.ModelChoiceField(queryset=MobTemplates.objects.all(), required=False, label="Spawner 1: Mob")
    spawner_count_2 = forms.IntegerField(required=False, label="Max Present", min_value=1)
    spawner_mob_3 = forms.ModelChoiceField(queryset=MobTemplates.objects.all(), required=False, label="Spawner 1: Mob")
    spawner_count_3 = forms.IntegerField(required=False, label="Max Present", min_value=1)
    spawner_mob_4 = forms.ModelChoiceField(queryset=MobTemplates.objects.all(), required=False, label="Spawner 1: Mob")
    spawner_count_4 = forms.IntegerField(required=False, label="Max Present", min_value=1)
    spawner_mob_5 = forms.ModelChoiceField(queryset=MobTemplates.objects.all(), required=False, label="Spawner 1: Mob")
    spawner_count_5 = forms.IntegerField(required=False, label="Max Present", min_value=1)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        room_instance = self.instance
        
        # When editing an existing room, filter the dropdowns by its area
        if room_instance and room_instance.pk and room_instance.area:
            qs = Rooms.objects.filter(area=room_instance.area)
            for direction in EXIT_DIRECTIONS:
                field_name = f'{direction}_exit'
                self.fields[field_name].queryset = qs
                # Pre-populate the form with the existing exit data
                if isinstance(room_instance.exits, dict):
                    if exit_id := room_instance.exits.get(direction):
                        self.initial[field_name] = exit_id
                
            if isinstance(room_instance.spawners, dict):
                    for i, (mob_id, spawn_info) in enumerate(room_instance.spawners.items(), 1):
                        if i > 5: break
                        try:
                            self.initial[f'spawner_mob_{i}'] = int(mob_id)
                            self.initial[f'spawner_count_{i}'] = spawn_info.get('max_present')
                        except (ValueError, TypeError):
                            continue
        
    
    class Meta:
        model = Rooms
        fields = '__all__'
        exclude = ['exits', 'spawners']

class MobTemplateAdminForm(forms.ModelForm):
    """A custom form for creating and editing Mob Templates."""

    stat_might = forms.IntegerField(label="Might", initial=10)
    stat_vitality = forms.IntegerField(label="Vitality", initial=10)
    stat_agility = forms.IntegerField(label="Agility", initial=10)
    stat_intellect = forms.IntegerField(label="Intellect", initial=10)
    stat_aura = forms.IntegerField(label="Aura", initial=10)
    stat_persona = forms.IntegerField(label="Persona", initial=10)

    flags = forms.MultipleChoiceField(
        choices=MOB_FLAG_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        required=False
    )
    
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

            if isinstance(mob_instance.stats, dict):
                for stat_name in STAT_NAMES:
                    self.initial[f'stat_{stat_name}'] = mob_instance.stats.get(stat_name, 10)

            if isinstance(mob_instance.flags, list):
                self.initial['flags'] = mob_instance.flags
            
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