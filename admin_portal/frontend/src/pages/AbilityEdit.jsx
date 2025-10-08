import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import api from '../api';

function AbilityEdit() {
    const { id } = useParams();
    const navigate = useNavigate();
    const [ability, setAbility] = useState(null);
    const [loading, setLoading] = useState(true);

    const classes = ['warrior', 'mage', 'rogue', 'cleric', 'ranger', 'paladin', 'bard', 'druid', 'barbarian'];

    useEffect(() => {
        api.get(`/abilities/${id}`)
        .then(response => {
            setAbility(response.data);
            setLoading(false);
        })
        .catch(error => {
            console.error('Error fetching ability:', error);
            setLoading(false);
        });
    }, [id]);

    const handleSubmit = async (e) => {
        e.preventDefault();
        try {
            const updateData = {
                internal_name: ability.internal_name,
                name: ability.name,
                ability_type: ability.ability_type,
                class_req: ability.class_req,
                level_req: ability.level_req,
                cost: ability.cost,
                target_type: ability.target_type,
                effect_type: ability.effect_type,
                effect_details: ability.effect_details,
                cast_time: ability.cast_time,
                roundtime: ability.roundtime,
                messages: ability.messages,
                description: ability.description,
        };

        await api.put(`/abilities/${id}`, updateData);
        alert('Ability updated successfully!');
        navigate('/abilities');
    } catch (error) {
        console.error('Error updating ability:', error);
        alert('Failed to update ability');
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

if (loading) return <div className="loading">Loading...</div>;
if (!ability) return <div className="error">Ability not found</div>;

return (
    <div className="ability-edit">
        <h2>Edit Ability: {ability.name}</h2>
        <form onSubmit={handleSubmit}>
            <label>
                Internal Name:
                <input
                type="text"
                value={ability.internal_name}
                onChange={(e) => setAbility({...ability, internal_name: e.target.value})}
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
                value={ability.description || ''}
                onChange={(e) => setAbility({...ability, description: e.target.value})}
                rows={3}
                />
            </label>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                <label>
                    Ability Type:
                    <select
                    value={ability.ability_type}
                    onChange={(e) => setAbility({...ability, ability_template: e.target.value})}
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
                    onChange={(e) => setAbility({...ability, target_type: e.target.value || null})}
                    >
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
                    />
                </label>

                <label>
                    Level Requirement:
                    <input
                    type="number"
                    value={ability.level_req}
                    onChange={(e) => setAbility({...ability, level_req: parseInt(e.target.value)})}
                    />
                </label>

                <label>
                    Cost:
                    <input
                    type="number"
                    value={ability.cost}
                    onChange={(e) => setAbility({...ability, cost: parseInt(e.target.value)})}
                    />
                </label>

                <label>
                    Cast Time:
                    <input
                    type="number"
                    step="0.1"
                    value={ability.cast_time}
                    onChange={(e) => setAbility({...ability, cast_time: parseFloat(e.target.value)})}
                    />
                </label>

                <label>
                    Roundtime:
                    <input
                    type="number"
                    step="0.1"
                    value={ability.roundtime}
                    onChange={(e) => setAbility({...ability, roundtime: parseFloat(e.target.value)})}
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
                            checked={ability.class_req?.includes(className)}
                            onChange={() => toggleClass(className)}
                            />
                            {className.charAt(0).toUpperCase() + className.slice(1)}
                        </label>
                    ))}
                </div>
            </div>

            <button type="submit">Save Changes</button>
            <button type="button" onClick={() => navigate('/abilities')}>Cancel</button>
        </form>
    </div>
    );
}

export default AbilityEdit;