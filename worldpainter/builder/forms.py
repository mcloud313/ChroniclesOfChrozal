# worldpainter/builder/forms.py
from django import forms
from .models import Rooms, MobTemplates, ItemTemplates

class RoomAdminForm(forms.ModelForm):
    # --- Spawner Fields ---
    spawner_1_mob = forms.ModelChoiceField(queryset=MobTemplates.objects.all(), required=False, label="Spawner 1: Mob")
    spawner_1_count = forms.IntegerField(min_value=1, required=False, label="Max Count")

    spawner_2_mob = forms.ModelChoiceField(queryset=MobTemplates.objects.all(), required=False, label="Spawner 2: Mob")
    spawner_2_count = forms.IntegerField(min_value=1, required=False, label="Max Count")

    spawner_3_mob = forms.ModelChoiceField(queryset=MobTemplates.objects.all(), required=False, label="Spawner 3: Mob")
    spawner_3_count = forms.IntegerField(min_value=1, required=False, label="Max Count")
    
    # You can add more spawner slots here if needed

    class Meta:
        model = Rooms
        # FIX: Explicitly list fields instead of using 'exclude'.
        # This ensures the form is aware of the 'spawners' field
        # but doesn't display its raw text box.
        fields = [
            'area', 'name', 'description', 'flags', 'coinage', 'spawners'
        ]
        widgets = {
            'spawners': forms.HiddenInput(),
        }


    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Populate the spawner fields from the existing JSON data
        if self.instance and self.instance.spawners:
            for i, (mob_id, spawn_info) in enumerate(self.instance.spawners.items(), 1):
                if i > 5: break
                try:
                    self.fields[f'spawner_{i}_mob'].initial = mob_id
                    self.fields[f'spawner_{i}_count'].initial = spawn_info.get('max_present')
                except (ValueError, TypeError, KeyError):
                    continue

    def save(self, commit=True):
        # Build the JSON from our form fields before saving
        spawners_json = {}
        for i in range(1, 6):
            # Use self.cleaned_data which is available after validation
            mob = self.cleaned_data.get(f'spawner_{i}_mob')
            count = self.cleaned_data.get(f'spawner_{i}_count')
            if mob and count:
                spawners_json[str(mob.id)] = {"max_present": count}
        
        # Assign the generated JSON to the instance's spawners field
        self.instance.spawners = spawners_json
        
        # Call the parent save method to save the instance to the database
        return super().save(commit)
    
class ItemTemplateAdminForm(forms.ModelForm):
    """A custom form to manage the 'stats' JSONField for ItemTemplates."""

    # Define individual fields for common item stats
    value = forms.IntegerField(required=False)
    weight = forms.FloatField(required=False)
    damage_base = forms.IntegerField(required=False)
    damage_rng = forms.IntegerField(required=False)
    speed = forms.FloatField(required=False)
    armor = forms.IntegerField(required=False)
    block_chance = forms.FloatField(required=False)
    
    # Bonus stats
    bonus_might = forms.IntegerField(required=False)
    bonus_vitality = forms.IntegerField(required=False)
    bonus_agility = forms.IntegerField(required=False)
    bonus_intellect = forms.IntegerField(required=False)
    bonus_aura = forms.IntegerField(required=False)
    bonus_persona = forms.IntegerField(required=False)


    class Meta:
        model = ItemTemplates
        fields = '__all__'
        widgets = {
            'stats': forms.HiddenInput(), # Hide the raw JSON field
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # If we are editing an existing item, populate our new fields from its stats JSON
        if self.instance and self.instance.stats:
            for key, value in self.instance.stats.items():
                if key in self.fields:
                    self.fields[key].initial = value

    def save(self, commit=True):
        # Build the stats JSON from our individual form fields before saving
        stats_json = {}
        for field_name in self.fields:
            # Only include fields that are part of the stats dictionary
            if field_name not in ['name', 'description', 'type', 'flags', 'damage_type']:
                 value = self.cleaned_data.get(field_name)
                 if value is not None and value != '':
                    stats_json[field_name] = value
        
        self.instance.stats = stats_json if stats_json else None
        return super().save(commit)
    
class MobTemplateAdminForm(forms.ModelForm):
    """A custom form to manage the 'stats' JSONField for MobTemplates."""
    
    # Define individual fields for mob stats
    might = forms.IntegerField(required=False)
    vitality = forms.IntegerField(required=False)
    agility = forms.IntegerField(required=False)
    intellect = forms.IntegerField(required=False)
    aura = forms.IntegerField(required=False)
    persona = forms.IntegerField(required=False)

    class Meta:
        model = MobTemplates
        fields = '__all__'
        widgets = {
            'stats': forms.HiddenInput(), # Hide the raw JSON field
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Populate fields from existing stats JSON
        if self.instance and self.instance.stats:
            for key, value in self.instance.stats.items():
                if key in self.fields:
                    self.fields[key].initial = value

    def save(self, commit=True):
        # Build the stats JSON from form fields
        stats_json = {}
        stat_fields = ['might', 'vitality', 'agility', 'intellect', 'aura', 'persona']
        for field_name in stat_fields:
            value = self.cleaned_data.get(field_name)
            if value is not None:
                stats_json[field_name] = value
        
        self.instance.stats = stats_json if stats_json else None
        return super().save(commit)