import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import api from '../api';

function MobEdit() {
    const { id } = useParams();
    const navigate = useNavigate();
    const [mob, setMob] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        api.get(`/mobs/${id}`)
            .then(response => {
                setMob(response.data);
                setLoading(false);
            })
            .catch(error => {
                console.error('Error fetching mob:', error);
                setLoading(false);
            });
    }, [id]);

    const handleSubmit = async (e) => {
        e.preventDefault();
        try {
            const updateData = {
                name: mob.name,
                description: mob.description,
                mob_type: mob.mob_type,
                level: mob.level,
                max_hp: mob.max_hp,
                max_coinage: mob.max_coinage,
                respawn_delay_seconds: mob.respawn_delay_seconds,
                movement_chance: mob.movement_chance,
                stats: mob.stats,
                resistances: mob.resistances,
                flags: mob.flags,
                variance: mob.variance
            };

            await api.put(`/mobs/${id}`, updateData);
            alert('Mob updated succesfully!');
            navigate('/mobs');
        } catch (error) {
            console.error('Error updating mob:', error);
            alert('Failed to update mob');
        }
    };

    const updateStat = (stat, value) => {
        setMob({
            ...mob,
            stats: {...mob.stats, [stat]: parseInt(value) || 10 }
        });
    };

    if (loading) return <div className="loading">Loading...</div>;
    if (!mob) return <div className="error">Mob not found</div>;

    return (
        <div className="mob-edit">
            <h2>Edit Mob: {mob.name}</h2>
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
                    value={mob.mob_type || ''}
                    onChange={(e) => setMob({...mob, mob_type: e.target.value})}
                    />
                </label>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem'}}>
                <label>
                Level:
                <input
                    type="number"
                    value={mob.level}
                    onChange={(e) => setMob({...mob, level: parseInt(e.target.value)})}
                    />
                </label>

                <label>
                    Max HP:
                    <input
                    type="number"
                    value={mob.max_hp}
                    onChange={(e) => setMob({...mob, max_hp: parseInt(e.target.value)})}
                />
                </label>

                <label>
                    Max Coinage:
                    <input
                    type="number"
                    value={mob.max_coinage}
                    onChange={(e) => setMob({...mob, max_coinage: parseInt(e.target.value)})}
                    />
                </label>

                <label>
                    Respawn Delay:
                    <input
                    type="number"
                    value={mob.respawn_delay_seconds}
                    onChange={(e) => setMob({...mob, respawn_delay_seconds: parseInt(e.target.value)})}
                    />
                </label>
                </div>

                <h3>Stats</h3>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '1rem' }}>
                    {mob.stats && Object.keys(mob.stats).map(stat => (
                        <label key={stat}>
                            {stat.charAt(0).toUpperCase() + stat.slice(1)}:
                            <input
                            type="number"
                            value={mob.stats[stat]}
                            onChange={(e) => updateStat(stat, e.target.value)}
                            />
                        </label>
                    ))}
                </div>

                <h3>Attacks ({mob.attacks?.length || 0})</h3>
                {mob.attacks && mob.attacks.length > 0 && (
                    <div style={{ background: '#d9c7a8', padding: '1rem', borderRadius: '4px', marginBottom: '1rem' }}>
                        {mob.attacks.map(attack => (
                            <div key={attack.id} style={{ marginBottom: '0.5rem' }}>
                                <strong>{attack.name}</strong> - {attack.damage_base}+{attack.damage_rng}d dmg, speed: {attack.speed}s
                                </div>
                        ))}
                    </div>
                )}

                <button type="submit">Save Changes</button>
                <button type="button" onClick={() => navigate('/mobs')}>Cancel</button>
            </form>
        </div>
    );
}

export default MobEdit;