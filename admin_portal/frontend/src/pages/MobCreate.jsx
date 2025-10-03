import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../api';

function MobCreate() {
    const navigate = useNavigate();
    const [mob, setMob] = useState({
        name: '',
        description: 'A creature.',
        mob_type: '',
        level: 1,
        max_hp: 10,
        max_coinage: 0,
        respawn_delay_seconds: 300,
        movement_chance: 0.0,
        stats: {
            might: 10,
            vitality: 10,
            agility: 10,
            intellect: 10,
            aura: 10,
            persona: 10
        },
        resistances: {},
        flags: [],
        variance: {}
    });

    const handleSubmit = async (e) => {
        e.preventDefault();
        try {
            const response = await api.post('/mobs/', mob);
            alert('Mob created successfully!');
            navigate(`/mobs/${response.data.id}`);
        } catch (error) {
            console.error('Error creating mob:', error);
            alert('Failed to create mob');
        }
    };

    const updateStat = (stat, value) =>  {
        setMob({
            ...mob,
            stats: { ...mob.stats, [stat]: parseInt(value) || 10 }
        });
    };

    return (
        <div className="mob-create">
            <h2>Create New Mob Template</h2>
            <form onSubmit={handleSubmit}>
                <label>
                    Name:
                <input
                    type="text"
                    value={mob.name}
                    onChange={(e) => setMob({...mob, name: e.target.value})}
                    required
                />
                </label>

                <label>
                    Description:
                    <textarea
                        value={mob.description}
                        onChange={(e) => setMob({...mob, description: e.target.value})}
                        rows={3}
                    />
                </label>

                <label>
                    Type:
                    <input
                        type="text"
                        value={mob.mob_type}
                        onChange={(e) => setMob({...mob, mob_type: e.target.value})}
                        placeholder="humanoid, beast, undead, etc."
                    />
                </label>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                    <label>
                        Level:
                        <input
                        type="number"
                        value={mob.level}
                        onChange={(e) => setMob({...mob, level: parseInt(e.target.value)})}
                        min="1"
                        />
                    </label>

                    <label>
                        Max HP:
                        <input
                        type="number"
                        value={mob.max_hp}
                        onChange={(e) => setMob({...mob, max_hp: parseInt(e.target.value)})}
                        min="1"
                        />
                    </label>

                    <label>
                        Max Coinage:
                        <input
                        type="number"
                        value={mob.max_coinage}
                        onChange={(e) => setMob({...mob, max_coinage: parseInt(e.target.value)})}
                        min="0"
                        />
                    </label>

                    <label>
                        Respawn Delay (seconds):
                        <input
                        type="number"
                        value={mob.respawn_delay_seconds}
                        onChange={(e) => setMob({...mob, respawn_delay_seconds: parseInt(e.target.value)})}
                        min="0"
                        />
                    </label>

                    <h3>Stats</h3>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '1rem' }}>
                        {Object.keys(mob.stats).map(stat => (
                            <label key={stat}>
                                {stat.charAt(0).toUpperCase() + stat.slice(1)}:
                                <input
                                type="number"
                                value={mob.stats[stat]}
                                onChange={(e) => updateStat(stat, e.target.value)}
                                min="1"
                            />
                        </label>
                    ))}
                    </div>
                </div>

                <button type="submit">Create Mob</button>
                <button type="button" onClick={() => navigate('/mobs')}>Cancel</button>
            </form>
        </div>
    );
}

export default MobCreate;