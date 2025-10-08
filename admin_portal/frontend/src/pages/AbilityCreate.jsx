import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../api';

function AbilityCreate() {
    const navigate = useNavigate();
    const [ability, setAbility] = useState({
        internal_name: '',
        name: '',
        ability_type: 'skill',
        class_req: [],
        level_req: 1,
        cost: 0,
        target_type: null,
        effect_type: null,
        effect_details: {},
        cost_time: 0.0,
        roundtime: 1.0,
        messages: {},
        description: ''
    });

    const classes = ['warrior', 'mage', 'rogue', 'cleric', 'ranger', 'paladin', 'bard', 'druid', 'barbarian'];

    const handleSubmit = async (e) => {
        e.preventDefault();
        try {
            const response = await api.post('/abilities/', ability);
            alert('Ability created successfully!');
            navigate(`/abilities/${response.data.id}`);
        } catch (error) {
            console.error('Error creating ability:', error);
            alert('Failed to create ability');
        }
    };

    const toggleClass = (className) => {
        if (ability.class_req.includes(className)) {
            setAbility({
                ...ability,
                class_req: ability.class_req.filter(c => c !== className)
            });
        } else {
            setAbility({
                ...ability,
                class_req: [...ability.class_req, className]
            });
        }
    };

    return (
        <div className="ability_create">
            <h2>Create New Ability</h2>
            <form onSubmit={handleSubmit}>
                <label>
                    Internal Name:
                    <input
                        type="text"
                        value={ability.internal_name}
                        onChange={(e) => setAbility({...ability, internal_name: e.target.value})}
                        placeholder="bash, fireball, heal, etc."
                        required
                    />
                </label>

                <label>
                    Display Name:
                    <input
                    type="text"
                    value={ability.name}
                    onChange={(e) => setAbility({...ability, name: e.target.value})}
                    required
                    />
                </label>

                <label>
                    Description:
                    <textarea
                    value={ability.description}
                    onChange={(e) => setAbility({...ability, description: e.target.value})}
                    rows={3}
                    />
                </label>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem'}}>
                   <label>
                    Ability Type:
                    <select
                    value={ability.ability_type}
                    onChange={(e) => setAbility({...ability, ability_type: e.target.value})}
                    >
                        <option value="skill">Skill</option>
                        <option value="spell">Spell</option>
                        <option value="passive">Passive</option>
                    </select>
                    </label>

                <label>
                    Target Type:
                    <select
                    value={ability.target_type || ''}
                    onChange={(e) => setAbility({...ability, target_type: e.target.value || null})}>
                        <option value="">None</option>
                        <option value="self">Self</option>
                        <option value="single">Single Target</option>
                        <option value="area">Area</option>
                    </select>
                </label>

                <label>
                    Effect Type:
                    <input
                    type="text"
                    value={ability.effect_type || ''}
                    onChange={(e) => setAbility({...ability, effect_type: e.target.value || null})}
                    placeholder="EFFECT_DAMAGE, EFFECT_HEAL, EFFECT_BUFF..."
                    />
                </label>

                <label>
                    Level Requirement:
                    <input
                    type="number"
                    value={ability.level_req}
                    onChange={(e) => setAbility({...ability, level_req: parseInt(e.target.value)})}
                    min="1"
                    />
                </label>

                <label>
                    Cost (Essence):
                    <input
                    type="number"
                    value={ability.cost}
                    onChange={(e) => setAbility({...ability, cost: parseInt(e.target.value)})}
                    min="0"
                    />
                </label>

                <label>
                    Cast Time (seconds):
                    <input
                    type="number"
                    step="0.1"
                    value={ability.cast_time}
                    onChange={(e) => setAbility({...ability, cast_time: parseFloat(e.target.value)})}
                    min="0"
                    />
                </label>
                </div>

                <div>
                    <h3>Class Requirements</h3>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '0.5rem' }}>
                        {classes.map(className => (
                            <label key={className} style={{ flexDirection: 'row', gap: '0.5rem', cursor: 'pointer' }}>
                                <input
                                type="checkbox"
                                checked={ability.class_req.includes(className)}
                                onChange={() => toggleClass(className)}
                                />
                                {className.charAt(0).toUpperCase() + className.slice(1)}
                            </label>
                        ))}
                    </div>
                </div>

                <button type="submit">Create Ability</button>
                <button type="button" onClick={() => navigate('/abilities')}>Cancel</button>
            </form>
        </div>
    )
}

export default AbilityCreate;