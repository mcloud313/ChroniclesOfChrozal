# worldpainter/builder/forms.py
from django import forms
from .models import Rooms, MobTemplates

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