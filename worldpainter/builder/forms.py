# worldpainter/builder/forms.py
from django import forms
from .models import Rooms, MobTemplates

class RoomAdminForm(forms.ModelForm):
    spwaner_1_mob = forms.ModelChoiceField(queryset=MobTemplates.objects.all(), required=False, label="Spawner 1: Mob")
    spawner_1_count = forms.IntegerField(min_value=1, required=False, label="Max Count")

    spawner_2_mob = forms.ModelChoiceField(queryset=MobTemplates.objects.all(), required=False, label="Spawner 2: Mob")
    spawner_2_count = forms.IntegerField(min_value=1, required=False, label="Max Count")

    spawner_3_mob = forms.ModelChoiceField(queryset=MobTemplates.objects.all(), required=False, label="Spawner 3: Mob")
    spawner_3_count = forms.IntegerField(min_value=1, required=False, label="Max Count")

    spawner_4_mob = forms.ModelChoiceField(queryset=MobTemplates.objects.all(), required=False, label="Spawner 4: Mob")
    spawner_4_count = forms.IntegerField(min_value=1, required=False, label="Max Count")

    spawner_5_mob = forms.ModelChoiceField(queryset=MobTemplates.objects.all(), required=False, label="Spawner 5: Mob")
    spawner_5_count = forms.IntegerField(min_value=1, required=False, label="Max Count")

    class Meta:
        model = Rooms
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # If editing a room that has spawners fill in the form fields.
        if self.instance and self.instance.spawners:
            for i, (mob_id, spawn_info) in enumerate(self.instance.spawners.items(), 1):
                if i > 5: break
                try:
                    self.fields[f'spawner_{i}_mob'].initial = mob_id
                    self.fields[f'spawner_{i}_count'].initial = spawn_info.get('max_present')
                except (ValueError, TypeError):
                    continue # Skip if data is malformed

    def save(self, commit=True):
        # When the form saves, build the JSON from our nice form fields
        spawners_json = {}
        for i in range(1, 6):
            mob = self.cleaned_data.get(f'spawner_{i}_mob')
            count = self.cleaned_data.get(f'spawner_{i}_count')
            if mob and count:
                spawners_json[str(mob.id)] = {"max_present": count}

        self.instance.spawners = spawners_json
        return super().save(commit)